"""Cutting report services owned by the Essdee customization layer.

This module contains only the Cutting report slice formerly hosted in the
Frappe 15 production_api utility module.  Base YRP remains unaware of these
garment-specific report structures.
"""

from __future__ import annotations

import copy
import json
import sys
from itertools import zip_longest

import frappe
from frappe.utils import getdate, sbool


def _require_report_access() -> None:
	"""Require the same read authority as the Cutting LaySheet data being reported."""

	frappe.has_permission("Cutting LaySheet", ptype="read", throw=True)


def update_if_string_instance(value):
	if isinstance(value, str):
		value = json.loads(value)

	return value or {}


def get_stich_details(ipd_doc):
	return {
		row.stiching_attribute_value: row.set_item_attribute_value
		for row in ipd_doc.stiching_item_details
	}


@frappe.whitelist()
def get_daily_production_report(date, location, items=None, lots=None, only_label_printed=False):
	_require_report_access()
	from essdee_yrp.essdee_yrp.doctype.lot.lot import fetch_order_item_details
	from essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan import get_complete_incomplete_structure
	from yrp.yrp.doctype.item.item import get_or_create_variant

	report_date = getdate(date)
	only_label_printed = sbool(only_label_printed)

	# Step 1: Single query to get CLS stats grouped by parent (CP or CO)
	filter_sql = ""
	filter_values = {"date": report_date}
	status_sql = " AND cls.status = 'Label Printed'" if only_label_printed else ""
	if items or lots:
		filter_parts = []
		if items:
			filter_values["filter_items"] = items
			filter_parts.append("cls.cutting_plan IN (SELECT cp.name FROM `tabCutting Plan` cp WHERE cp.item IN %(filter_items)s)")
			filter_parts.append("cls.cutting_order IN (SELECT co.name FROM `tabCutting Order` co WHERE co.item IN %(filter_items)s)")
		if lots:
			filter_values["filter_lots"] = lots
			filter_parts.append("cls.cutting_plan IN (SELECT cp.name FROM `tabCutting Plan` cp WHERE cp.lot IN %(filter_lots)s)")
		if filter_parts:
			filter_sql = f" AND ({' OR '.join(filter_parts)})"

	cls_stats_rows = frappe.db.sql(f"""
		SELECT cls.cutting_plan, cls.cutting_order,
			GROUP_CONCAT(cls.name) as names,
			COUNT(*) as bundle_count,
			SUM(CASE WHEN cls.status = 'Label Printed' THEN 1 ELSE 0 END) as label_count,
			SUM(CASE WHEN cls.posting_date = %(date)s THEN 1 ELSE 0 END) as created_count
		FROM `tabCutting LaySheet` cls
		WHERE cls.bundle_generated_date = %(date)s{filter_sql}{status_sql}
		AND cls.status != 'Cancelled'
		GROUP BY cls.cutting_plan, cls.cutting_order
	""", filter_values, as_dict=True)

	if not cls_stats_rows:
		return {"report_data": [], "bundle_generated": 0, "label_printed": 0, "created": 0}

	# Map by (parent_dt, parent_name)
	cls_stats_map = {}
	for row in cls_stats_rows:
		if row['cutting_plan']:
			key = ("Cutting Plan", row['cutting_plan'])
		elif row['cutting_order']:
			key = ("Cutting Order", row['cutting_order'])
		else:
			continue
		cls_stats_map[key] = row

	# Step 2: Bulk-fetch all CLS bundle data
	all_cls_names = []
	for stat in cls_stats_map.values():
		all_cls_names.extend(stat['names'].split(','))

	bundles_by_parent = {}
	if all_cls_names:
		bundles = frappe.db.sql("""
			SELECT parent, part, size, quantity, set_combination
			FROM `tabCutting LaySheet Bundle`
			WHERE parent IN %(names)s
		""", {"names": all_cls_names}, as_dict=True)
		for b in bundles:
			bundles_by_parent.setdefault(b['parent'], []).append(b)

	# Step 3: Batch-fetch Work Order calculated items (CP only)
	cp_names = [name for dt, name in cls_stats_map.keys() if dt == "Cutting Plan"]
	wo_planned_by_cp = {}
	if cp_names:
		wo_map_rows = frappe.db.sql("""
			SELECT cp.name as cp_name, cp.work_order,
				woci.item_variant, woci.quantity, woci.received_qty
			FROM `tabCutting Plan` cp
			JOIN `tabWork Order Calculated Item` woci ON woci.parent = cp.work_order
			WHERE cp.name IN %(cp_names)s AND cp.work_order IS NOT NULL AND cp.work_order != ''
		""", {"cp_names": cp_names}, as_dict=True)
		for row in wo_map_rows:
			wo_planned_by_cp.setdefault(row['cp_name'], {})[row['item_variant']] = {
				"planned": row['quantity'], "cumulative": row['received_qty']
			}

	# Step 4: Variant cache
	variant_cache = {}
	def cached_get_variant(template, args):
		key = (template, tuple(sorted(args.items())))
		if key not in variant_cache:
			variant_cache[key] = get_or_create_variant(template, args)
		return variant_cache[key]

	report = []
	bundle_generated = 0
	label_printed = 0
	created = 0

	for (parent_dt, parent_name), stats in cls_stats_map.items():
		if parent_dt == "Cutting Plan":
			cp_doc = frappe.get_doc("Cutting Plan", parent_name)
			if cp_doc.version == "V1":
				frappe.throw("Can't get report for Cutting Plan Version V1")
			if location and cp_doc.cutting_location != location:
				continue
			detail_doc = frappe.get_cached_doc("Item Production Detail", cp_doc.production_detail)
			item_details = fetch_order_item_details(cp_doc.items, cp_doc.production_detail)
			completed, incomplete = get_complete_incomplete_structure(cp_doc.production_detail, item_details)
			incomplete_items = update_if_string_instance(incomplete)
			completed_items = update_if_string_instance(completed)
			parent_item = cp_doc.item
			parent_lot = cp_doc.lot
			parent_location = cp_doc.cutting_location
			planned_dict = wo_planned_by_cp.get(parent_name, {})
		else:
			co_doc = frappe.get_doc("Cutting Order", parent_name)
			if location and co_doc.cutting_location != location:
				continue
			detail_doc = frappe.get_cached_doc("Cutting Order Detail", co_doc.cutting_order_detail)
			completed_items = update_if_string_instance(co_doc.completed_items_json)
			incomplete_items = update_if_string_instance(co_doc.incomplete_items_json)
			# Enrich CO structure to match CP format expected by Vue template
			attr_list = [detail_doc.packing_attribute]
			if detail_doc.is_set_item and detail_doc.set_item_attribute:
				attr_list.append(detail_doc.set_item_attribute)
			completed_items.setdefault('attributes', attr_list)
			completed_items.setdefault('primary_attribute', detail_doc.primary_attribute)
			for item in completed_items.get('items', []):
				item.setdefault('is_set_item', detail_doc.is_set_item)
				item.setdefault('set_attr', detail_doc.set_item_attribute if detail_doc.is_set_item else None)
				item.setdefault('pack_attr', detail_doc.packing_attribute)
				item.setdefault('major_attr_value', None)
				item.setdefault('primary_attribute', detail_doc.primary_attribute)
				if item.get('item_keys') is None:
					colour = item.get('attributes', {}).get(detail_doc.packing_attribute, '')
					item['item_keys'] = {'major_colour': colour}
			parent_item = co_doc.item
			parent_lot = ''
			parent_location = co_doc.cutting_location
			planned_dict = {}

		bundle_generated += stats['bundle_count']
		label_printed += stats['label_count']
		created += stats['created_count']

		cls_name_list = [{'name': n} for n in stats['names'].split(',')]
		completed_items, incomplete_items = calculate_completed(cls_name_list, detail_doc, completed_items, incomplete_items, bundles_by_parent)

		major_panel = {}
		panel_qty = {}
		for row in detail_doc.stiching_item_details:
			if row.is_default:
				major_panel[row.set_item_attribute_value] = row.stiching_attribute_value
			panel_qty[row.stiching_attribute_value] = row.quantity

		if not detail_doc.is_set_item:
			if hasattr(detail_doc, 'stiching_major_attribute_value') and detail_doc.stiching_major_attribute_value:
				major_panel['panel'] = detail_doc.stiching_major_attribute_value
			else:
				# COD may not have stiching_major_attribute_value; derive from is_default or first panel
				for row in detail_doc.stiching_item_details:
					if row.is_default:
						major_panel['panel'] = row.stiching_attribute_value
						break
				if 'panel' not in major_panel and detail_doc.stiching_item_details:
					major_panel['panel'] = detail_doc.stiching_item_details[0].stiching_attribute_value

		for row1, row2 in zip_longest(completed_items['items'], incomplete_items['items']):
			row1['values1'] = {}
			if detail_doc.is_set_item:
				part = row1['attributes'][detail_doc.set_item_attribute]
				panel = major_panel[part]
				for size in row1['values']:
					if row2['values'][size][panel] > 0:
						row1['values'][size] += row2['values'][size][panel]
						x = get_less_qty_panels(row2['values'][size], panel, panel_qty)
						row1['values1'][size] = x
			else:
				for size in row1['values']:
					if row2['values'][size][major_panel['panel']] > 0:
						row1['values'][size] += row2['values'][size][major_panel['panel']]
						x = get_less_qty_panels(row2['values'][size], major_panel['panel'], panel_qty)
						row1['values1'][size] = x

		items_list = []
		total = 0
		total_planned_qty = 0
		total_received_qty = 0

		for row in completed_items['items']:
			total_qty = 0
			total_planned = 0
			total_received = 0
			for val in row['values']:
				if row['values'][val] > 0:
					total_qty += row['values'][val]
					if planned_dict:
						attrs = row['attributes']
						attrs[row['primary_attribute']] = val
						variant = cached_get_variant(parent_item, attrs)
						if variant in planned_dict:
							total_planned += planned_dict[variant]['planned']
							total_received += planned_dict[variant]['cumulative']

			if total_qty > 0:
				row['total_qty'] = total_qty
				row['planned'] = total_planned
				row['cumulative'] = total_received
				items_list.append(row)
				total += total_qty
				total_planned_qty += total_planned
				total_received_qty += total_received

		if len(items_list) == 0:
			continue
		else:
			completed_items['items'] = items_list
		completed_items['total_sum'] = total
		completed_items['total_planned_sum'] = total_planned_qty
		completed_items['total_received_sum'] = total_received_qty
		completed_items['style_no'] = parent_item
		completed_items['lot_no'] = parent_lot
		completed_items['location'] = parent_location
		report.append(completed_items)

	return {
		"report_data": report,
		"bundle_generated": bundle_generated,
		"label_printed": label_printed,
		"created": created
	}

@frappe.whitelist()
def get_daily_production_summary_report(items=None, lots=None, location=None, from_date=None, to_date=None):
	_require_report_access()
	import json as _json

	items_list = _json.loads(items) if items else []
	lots_list = _json.loads(lots) if lots else []

	has_date_range = bool(from_date and to_date)

	if not items_list and not lots_list and not has_date_range:
		frappe.throw("Please select at least one Item or Lot, or a From Date and To Date range")

	conditions = []
	values = {}
	if items_list:
		conditions.append("item IN %(items)s")
		values["items"] = items_list
	if lots_list:
		conditions.append("lot IN %(lots)s")
		values["lots"] = lots_list

	where_clause = "(" + " OR ".join(conditions) + ")" if conditions else "1=1"

	extra_filters = ""
	if from_date:
		extra_filters += " AND bundle_generated_date >= %(from_date)s"
		values["from_date"] = getdate(from_date)
	if to_date:
		extra_filters += " AND bundle_generated_date <= %(to_date)s"
		values["to_date"] = getdate(to_date)

	dates = frappe.db.sql(
		f"""
			SELECT DISTINCT bundle_generated_date
			FROM `tabCutting LaySheet`
			WHERE {where_clause}
			AND bundle_generated_date IS NOT NULL
			{extra_filters}
			AND status = 'Label Printed'
			ORDER BY bundle_generated_date DESC
		""",
		values,
		as_dict=True,
	)

	result = []
	for row in dates:
		d = row["bundle_generated_date"]
		data = get_daily_production_report(str(d), location, items=items_list or None, lots=lots_list or None, only_label_printed=True)
		if items_list or lots_list:
			filtered = [
				entry for entry in data["report_data"]
				if entry.get("style_no") in items_list or entry.get("lot_no") in lots_list
			]
		else:
			filtered = data["report_data"]
		if filtered:
			result.append({
				"date": str(d),
				"report_data": filtered,
				"bundle_generated": data["bundle_generated"],
				"label_printed": data["label_printed"],
				"created": data["created"],
			})

	return result

@frappe.whitelist()
def get_cutting_detail_report(start_date, end_date, location):
	_require_report_access()
	from essdee_yrp.essdee_yrp.doctype.lot.lot import fetch_order_item_details
	from essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan import get_complete_incomplete_structure
	cutting_plans = frappe.db.sql(
		"""
			SELECT distinct(cutting_plan) FROM `tabCutting LaySheet` WHERE bundle_generated_date BETWEEN %(start_date)s AND %(end_date)s
			AND status = 'Label Printed'
		""", {
			"start_date": getdate(start_date),
			"end_date": getdate(end_date)
		}, as_dict=True
	)
	report = []
	bundle_generated = 0
	label_printed = 0
	created = 0
	for cutting_plan in cutting_plans:
		cp_doc = frappe.get_doc("Cutting Plan",cutting_plan['cutting_plan'])
		if cp_doc.version == "V1":
			frappe.throw("Can't get report for Cutting Plan Version V1")
		if location and cp_doc.cutting_location != location:
			continue
		item_details = fetch_order_item_details(cp_doc.items,cp_doc.production_detail)
		completed, incomplete = get_complete_incomplete_structure(cp_doc.production_detail,item_details)
		incomplete_items = update_if_string_instance(incomplete)
		completed_items = update_if_string_instance(completed)
		production_detail = cp_doc.production_detail
		ipd_doc = frappe.get_cached_doc("Item Production Detail",production_detail)
		cls_list = frappe.db.sql(
			"""
				SELECT name FROM `tabCutting LaySheet` WHERE bundle_generated_date BETWEEN %(start_date)s AND %(end_date)s
				AND cutting_plan = %(cutting_plan)s AND status = 'Label Printed'
			""", {
				"start_date": getdate(start_date),
				"end_date": getdate(end_date),
				"cutting_plan": cutting_plan['cutting_plan']
			}, as_dict=True
		)
		bundle_generated += len(cls_list)
		cls_list2 = frappe.db.sql(
			"""
				SELECT name FROM `tabCutting LaySheet` WHERE bundle_generated_date BETWEEN %(start_date)s AND %(end_date)s
				AND cutting_plan = %(cutting_plan)s AND status = 'Label Printed'
			""", {
				"start_date": getdate(start_date),
				"end_date": getdate(end_date),
				"cutting_plan": cutting_plan['cutting_plan']
			}, as_dict=True
		)
		label_printed += len(cls_list2)
		cls_list3 = frappe.db.sql(
			"""
				SELECT name FROM `tabCutting LaySheet` WHERE posting_date BETWEEN %(start_date)s AND %(end_date)s
				AND cutting_plan = %(cutting_plan)s AND status = 'Label Printed'
			""", {
				"start_date": getdate(start_date),
				"end_date": getdate(end_date),
				"cutting_plan": cutting_plan['cutting_plan']
			}, as_dict=True
		)
		created += len(cls_list3)
		completed_items, incomplete_items = calculate_completed(cls_list, ipd_doc, completed_items, incomplete_items)
		major_panel = {}
		panel_qty = {}
		for row in ipd_doc.stiching_item_details:
			if row.is_default:
				major_panel[row.set_item_attribute_value] = row.stiching_attribute_value
			panel_qty[row.stiching_attribute_value] = row.quantity

		if not ipd_doc.is_set_item:
			major_panel['panel'] = ipd_doc.stiching_major_attribute_value

		for row1, row2 in zip_longest(completed_items['items'], incomplete_items['items']):
			row1['values1'] = {}
			if ipd_doc.is_set_item:
				part = row1['attributes'][ipd_doc.set_item_attribute]
				panel = major_panel[part]
				for size in row1['values']:
					if row2['values'][size][panel] > 0:
						row1['values'][size] += row2['values'][size][panel]
						x = get_less_qty_panels(row2['values'][size], panel, panel_qty)
						row1['values1'][size] = x
			else:
				for size in row1['values']:
					if row2['values'][size][major_panel['panel']] > 0:
						row1['values'][size] += row2['values'][size][major_panel['panel']]
						x = get_less_qty_panels(row2['values'][size], major_panel['panel'], panel_qty)
						row1['values1'][size] = x

		items_list = []
		total = 0
		total_planned_qty = 0
		total_received_qty = 0
		planned_dict = {}
		if cp_doc.work_order:
			wo_doc = frappe.get_doc("Work Order", cp_doc.work_order)
			for row in wo_doc.work_order_calculated_items:
				planned_dict.setdefault(row.item_variant, {
					"planned": row.quantity,
					"cumulative": row.received_qty
				})
		from yrp.yrp.doctype.item.item import get_or_create_variant
		for row in completed_items['items']:
			total_qty = 0
			total_planned = 0
			total_received = 0
			for val in row['values']:
				if row['values'][val] > 0:
					total_qty += row['values'][val]
					attrs = row['attributes']
					attrs[row['primary_attribute']] = val
					variant = get_or_create_variant(cp_doc.item, attrs)
					if planned_dict and variant in planned_dict:
						total_planned += planned_dict[variant]['planned']
						total_received += planned_dict[variant]['cumulative']

			if total_qty > 0:
				row['total_qty'] = total_qty
				row['planned'] = total_planned
				row['cumulative'] = total_received
				items_list.append(row)
				total += total_qty
				total_planned_qty += total_planned
				total_received_qty += total_received

		if len(items_list) == 0:
			continue
		else:
			completed_items['items'] = items_list
		completed_items['total_sum'] = total
		completed_items['total_planned_sum'] = total_planned_qty
		completed_items['total_received_sum'] = total_received_qty
		completed_items['style_no'] = cp_doc.item
		completed_items['lot_no'] = cp_doc.lot
		completed_items['location'] = cp_doc.cutting_location
		report.append(completed_items)

	return {
		"report_data": report,
		"bundle_generated": bundle_generated,
		"label_printed": label_printed,
		"created": created
	}

def get_less_qty_panels(values, major_panel, panel_qty):
	result = []
	major_panel_qty = values[major_panel]
	for panel in values:
		if panel == major_panel:
			continue

		if panel_qty[major_panel] == panel_qty[panel]:
			if values[panel] < major_panel_qty:
				result.append({
					"panel": panel,
					"qty": major_panel_qty - values[panel]
				})
		elif panel_qty[major_panel] < panel_qty[panel]:
			diff = panel_qty[panel] - panel_qty[major_panel]
			qty = major_panel_qty
			while diff > 0:
				qty = qty + major_panel_qty
				diff = diff - 1
			if qty > values[panel]:
				result.append({
					"panel": panel,
					"qty": qty - values[panel]
				})

	return result

def calculate_completed(cls_list, ipd_doc, completed_items, incomplete_items, bundles_by_parent=None):
	for cls in cls_list:
		# Use pre-fetched bundle data if available, otherwise fall back to get_doc
		if bundles_by_parent is not None:
			cls_bundles = bundles_by_parent.get(cls['name'], [])
		else:
			cls_doc = frappe.get_doc("Cutting LaySheet", cls['name'])
			cls_bundles = cls_doc.cutting_laysheet_bundles
		if not ipd_doc.is_set_item:
			alter_incomplete_items = {}
			for item in incomplete_items['items']:
				colour = item['attributes'][ipd_doc.packing_attribute]
				alter_incomplete_items[colour] = item['values']

			for item in cls_bundles:
				parts = item.part.split(",")
				set_combination = update_if_string_instance(item.set_combination)
				set_colour = set_combination['major_colour']
				qty = item.quantity
				for part in parts:
					alter_incomplete_items[set_colour][item.size][part] += qty
			total_qty = completed_items['total_qty']
			for item in completed_items['items']:
				colour = item['attributes'][ipd_doc.packing_attribute]
				for val in item['values']:
					min = sys.maxsize
					if not alter_incomplete_items[colour].get(val):
						continue
					for panel in alter_incomplete_items[colour][val]:
						if alter_incomplete_items[colour][val][panel] < min:
							min = alter_incomplete_items[colour][val][panel]
					total_qty.setdefault(val, 0)
					total_qty[val] += min
					item['values'][val] += min
					for panel in alter_incomplete_items[colour][val]:
						alter_incomplete_items[colour][val][panel] -= min
			completed_items['total_qty'] = total_qty
			for item in incomplete_items['items']:
				colour = item['attributes'][ipd_doc.packing_attribute]
				item['values'] = alter_incomplete_items[colour]
		else:
			stich_details = get_stich_details(ipd_doc)
			alter_incomplete_items = {}
			for item in incomplete_items['items']:
				set_combination = update_if_string_instance(item['item_keys'])
				colour = set_combination['major_colour']
				part = item['attributes'][ipd_doc.set_item_attribute]
				if alter_incomplete_items.get(colour):
					alter_incomplete_items[colour][part] = item['values']
				else:
					alter_incomplete_items[colour] = {}
					alter_incomplete_items[colour][part] = item['values']
			for item in cls_bundles:
				parts = item.part.split(",")
				set_combination = update_if_string_instance(item.set_combination)
				major_part = set_combination['major_part']
				major_colour = set_combination['major_colour']
				d = {
					"major_colour": major_colour,
				}
				if set_combination.get('set_part'):
					major_part = set_combination['set_part']
					major_colour = set_combination['set_colour']
				d['major_part'] = major_part

				qty = item.quantity
				for part in parts:
					try:
						alter_incomplete_items[d['major_colour']][d['major_part']][item.size][part] += qty
					except:
						secondary_part = stich_details[part]
						alter_incomplete_items[d['major_colour']][secondary_part][item.size][part] += qty

			total_qty = completed_items['total_qty']
			for item in completed_items['items']:
				set_combination = update_if_string_instance(item['item_keys'])
				colour = set_combination['major_colour']
				part = item['attributes'][ipd_doc.set_item_attribute]
				for val in item['values']:
					min = sys.maxsize
					for panel in alter_incomplete_items[colour][part][val]:
						if alter_incomplete_items[colour][part][val][panel] < min:
							min = alter_incomplete_items[colour][part][val][panel]

					total_qty.setdefault(val, 0)
					total_qty[val] += min
					item['values'][val] += min
					for panel in alter_incomplete_items[colour][part][val]:
						alter_incomplete_items[colour][part][val][panel] -= min

			completed_items["total_qty"] = total_qty
			for item in incomplete_items['items']:
				set_combination = update_if_string_instance(item['item_keys'])
				colour = set_combination['major_colour']
				part = item['attributes'][ipd_doc.set_item_attribute]
				item['values'] = alter_incomplete_items[colour][part]

	return completed_items, incomplete_items

@frappe.whitelist()
def get_cut_sheet_report(date, location):
	_require_report_access()
	from essdee_yrp.essdee_yrp.doctype.lot.lot import fetch_order_item_details
	from essdee_yrp.essdee_yrp.doctype.cutting_plan.cutting_plan import get_complete_incomplete_structure

	report_date = getdate(date)

	# Get all parents (CP and CO) for CLS on this date
	parent_rows = frappe.db.sql("""
		SELECT DISTINCT cutting_plan, cutting_order
		FROM `tabCutting LaySheet`
		WHERE bundle_generated_date = %(date)s
	""", {"date": report_date}, as_dict=True)

	report = []
	for parent_row in parent_rows:
		if parent_row['cutting_plan']:
			parent_dt = "Cutting Plan"
			parent_name = parent_row['cutting_plan']
			cp_doc = frappe.get_doc("Cutting Plan", parent_name)
			if cp_doc.version == "V1":
				frappe.throw("Can't get report for Cutting Plan Version V1")
			if location and cp_doc.cutting_location != location:
				continue
			item_details = fetch_order_item_details(cp_doc.items, cp_doc.production_detail)
			completed, incomplete = get_complete_incomplete_structure(cp_doc.production_detail, item_details)
			incomplete_items = update_if_string_instance(incomplete)
			detail_doc = frappe.get_cached_doc("Item Production Detail", cp_doc.production_detail)
			parent_item = cp_doc.item
			parent_lot = cp_doc.lot
			parent_location = cp_doc.cutting_location
			parent_field = "cutting_plan"
		elif parent_row['cutting_order']:
			parent_dt = "Cutting Order"
			parent_name = parent_row['cutting_order']
			co_doc = frappe.get_doc("Cutting Order", parent_name)
			if location and co_doc.cutting_location != location:
				continue
			incomplete_items = update_if_string_instance(co_doc.incomplete_items_json)
			detail_doc = frappe.get_cached_doc("Cutting Order Detail", co_doc.cutting_order_detail)
			# Enrich CO structure to match CP format expected by Vue template
			attr_list = [detail_doc.packing_attribute]
			if detail_doc.is_set_item and detail_doc.set_item_attribute:
				attr_list.append(detail_doc.set_item_attribute)
			incomplete_items.setdefault('attributes', attr_list)
			incomplete_items.setdefault('primary_attribute', detail_doc.primary_attribute)
			for item in incomplete_items.get('items', []):
				item.setdefault('is_set_item', detail_doc.is_set_item)
				item.setdefault('set_attr', detail_doc.set_item_attribute if detail_doc.is_set_item else None)
				item.setdefault('pack_attr', detail_doc.packing_attribute)
				item.setdefault('major_attr_value', None)
				item.setdefault('primary_attribute', detail_doc.primary_attribute)
				if item.get('item_keys') is None:
					colour = item.get('attributes', {}).get(detail_doc.packing_attribute, '')
					item['item_keys'] = {'major_colour': colour}
			parent_item = co_doc.item
			parent_lot = ''
			parent_location = co_doc.cutting_location
			parent_field = "cutting_order"
		else:
			continue

		cls_list = frappe.db.sql(f"""
			SELECT name FROM `tabCutting LaySheet`
			WHERE bundle_generated_date = %(date)s AND {parent_field} = %(parent_name)s
		""", {"date": report_date, "parent_name": parent_name}, as_dict=True)

		alter_incomplete_items = {}
		if not detail_doc.is_set_item:
			for item in incomplete_items['items']:
				colour = item['attributes'][detail_doc.packing_attribute]
				alter_incomplete_items[colour] = item['values']
		else:
			for item in incomplete_items['items']:
				set_combination = update_if_string_instance(item['item_keys'])
				colour = set_combination['major_colour']
				part = item['attributes'][detail_doc.set_item_attribute]
				if alter_incomplete_items.get(colour):
					alter_incomplete_items[colour][part] = item['values']
				else:
					alter_incomplete_items[colour] = {}
					alter_incomplete_items[colour][part] = item['values']

		for cls in cls_list:
			cls_doc = frappe.get_doc("Cutting LaySheet", cls['name'])
			if not detail_doc.is_set_item:
				for item in cls_doc.cutting_laysheet_bundles:
					parts = item.part.split(",")
					set_combination = update_if_string_instance(item.set_combination)
					set_colour = set_combination['major_colour']
					qty = item.quantity
					for part in parts:
						alter_incomplete_items[set_colour][item.size][part] += qty
				for item in incomplete_items['items']:
					colour = item['attributes'][detail_doc.packing_attribute]
					item['values'] = alter_incomplete_items[colour]

			else:
				stich_details = get_stich_details(detail_doc)
				for item in cls_doc.cutting_laysheet_bundles:
					parts = item.part.split(",")
					set_combination = update_if_string_instance(item.set_combination)
					major_part = set_combination['major_part']
					major_colour = set_combination['major_colour']
					d = {
						"major_colour": major_colour,
					}
					if set_combination.get('set_part'):
						major_part = set_combination['set_part']
						major_colour = set_combination['set_colour']
					d['major_part'] = major_part

					qty = item.quantity
					for part in parts:
						try:
							alter_incomplete_items[d['major_colour']][d['major_part']][item.size][part] += qty
						except:
							secondary_part = stich_details[part]
							alter_incomplete_items[d['major_colour']][secondary_part][item.size][part] += qty

				for item in incomplete_items['items']:
					set_combination = update_if_string_instance(item['item_keys'])
					colour = set_combination['major_colour']
					part = item['attributes'][detail_doc.set_item_attribute]
					item['values'] = alter_incomplete_items[colour][part]

		items_list = []
		for item in incomplete_items['items']:
			add_item = False
			for size in item['values']:
				check = False
				for panel in item['values'][size]:
					if item['values'][size][panel] > 0:
						check = True
						break
				if check:
					add_item = True
					break
			if add_item:
				items_list.append(item)

		if len(items_list) == 0:
			continue

		incomplete_items['items'] = items_list

		for item in incomplete_items['items']:
			item['total_panel_qty'] = {}
			for size in item['values']:
				for panel in item['values'][size]:
					if item['values'][size][panel] > 0:
						item['total_panel_qty'].setdefault(panel, 0)
						item['total_panel_qty'][panel] += item['values'][size][panel]
		incomplete_items['style_no'] = parent_item
		incomplete_items['lot_no'] = parent_lot
		incomplete_items['location'] = parent_location
		report.append(incomplete_items)

	return report

@frappe.whitelist()
def get_multiccr(open_status=None, lot_list=None, item_list=None, category=None):
	_require_report_access()
	conditions = ""
	con = {}
	if category:
		conditions += " AND t2.product_category = %(category)s"
		con = {
			"category": category
		}
	lot_list = update_if_string_instance(lot_list)
	item_list = update_if_string_instance(item_list)

	if lot_list:
		lot_list.append("")
		conditions += " AND t1.name IN %(lot_list)s"
		con['lot_list'] = tuple(lot_list)

	if item_list:
		item_list.append("")
		conditions += " AND t1.item IN %(item_list)s"
		con['item_list'] = tuple(item_list)

	if open_status:
		conditions += " AND t1.status = %(status)s"
		con['status'] = open_status

	lot_list = frappe.db.sql(
		f"""
			SELECT t1.name FROM `tabLot` t1 JOIN `tabItem` t2 ON t1.item = t2.name
			WHERE 1 = 1 {conditions} AND (t1.production_detail IS NOT NULL AND t1.production_detail != '')
		""", con, as_dict=True
	)
	lot_data = {}
	output_lots = []
	output_items = []
	for lot in lot_list:
		lot = lot['name']
		cp_list = frappe.get_all("Cutting Plan", filters={
			"lot": lot,
			"docstatus": 1,
		}, pluck="name")
		total_qty = 0
		for cp in cp_list:
			if lot not in output_lots:
				output_lots.append(lot)
			cp_fields = [
				'item',
				'lay_no',
				'no_of_colours',
				'completed_items_json',
				'version',
				'production_detail',
			]
			(
				item_name,
				lay_no,
				no_of_colours,
				completed,
				version,
				production_detail,
			) = frappe.get_value("Cutting Plan", cp, cp_fields)
			if item_name not in output_items:
				output_items.append(item_name)
			completed = [update_if_string_instance(completed)]
			for row in completed:
				if not row['is_set_item']:
					for item in row['items']:
						total = 0
						for size in item['values']:
							total += item['values'][size]
						item['total_qty'] = total
						total_qty += total
				else:
					set_attribute = row.get('set_item_attr') or frappe.get_cached_value(
						"Item Production Detail",
						production_detail,
						"set_item_attribute",
					)
					for part in row['Panel']:
						for item in row['items']:
							if item['attributes'][set_attribute] == part:
								total = 0
								for size in item['values']:
									total += item['values'][size]
								item['total_qty'] = total
								total_qty += total
			cloth_details = frappe.get_all(
				"Cutting Plan Cloth Detail",
				filters={
					"parent": cp,
					"parenttype": "Cutting Plan",
					"parentfield": "cutting_plan_cloth_details",
				},
				fields=[
					"cloth_item_variant",
					"cloth_type",
					"dia",
					"colour",
					"required_weight",
					"weight",
					"used_weight",
					"balance_weight",
				],
			)
			lot_data = get_lot_data(
						lot,
						lot_data,
						cloth_details,
						completed,
						item_name,
						lay_no,
						no_of_colours,
						version,
						total_qty
					)

	item_data = get_item_data(lot_data)

	d = {
		"output_lots": output_lots,
		"output_items": output_items,
		"data": lot_data,
		"item_data": item_data,
	}
	return d

def get_item_data(lot_data):
	item_data = {}
	import copy
	lot_details = copy.deepcopy(lot_data)
	for lot in lot_details:
		item_name = lot_details[lot]['item']
		if item_name not in item_data:
			item_data[item_name] = {
				"completed_json": lot_details[lot]['completed_json'],
				"total_qty": lot_details[lot]['total_qty'],
				"cloth_details": lot_details[lot]['cloth_details'],
				"cloth_total": lot_details[lot]['cloth_total'],
			}
		else:
			item_data[item_name]['total_qty'] += lot_details[lot]['total_qty']
			d = {}
			old_details = item_data[item_name]['cloth_details']
			for row in old_details:
				key = (row['cloth_item_variant'], row['cloth_type'])
				d[key] = row

			for row in lot_details[lot]['cloth_details']:
				key = (row['cloth_item_variant'], row['cloth_type'])
				if key in d:
					d[key]['used_weight'] += row['used_weight']
					d[key]['weight'] += row['weight']
					d[key]['required_weight'] += row['required_weight']
				else:
					d[key] = row
			item_data[item_name]['cloth_total']['balance'] = 0
			item_data[item_name]['cloth_total']['received'] = 0
			item_data[item_name]['cloth_total']['used'] = 0
			item_data[item_name]['cloth_total']['required'] = 0
			for key in d:
				row = d[key]
				row['balance_weight'] = round(row['weight'] - row['used_weight'], 3)
				item_data[item_name]['cloth_total']['balance'] += row['balance_weight']
				item_data[item_name]['cloth_total']['received'] += row['weight']
				item_data[item_name]['cloth_total']['used'] += row['used_weight']
				item_data[item_name]['cloth_total']['required'] += row['required_weight']

			item_data[item_name]['cloth_details'] = d.values()

			old_json = item_data[item_name]['completed_json'][0]
			new_json = lot_details[lot]['completed_json'][0]
			old_items = {
				(
					json.dumps(item.get('attributes') or {}, sort_keys=True),
					json.dumps(item.get('item_keys') or {}, sort_keys=True),
				): item
				for item in old_json['items']
			}
			for new_item in new_json['items']:
				key = (
					json.dumps(new_item.get('attributes') or {}, sort_keys=True),
					json.dumps(new_item.get('item_keys') or {}, sort_keys=True),
				)
				old_item = old_items.get(key)
				if old_item is None:
					old_item = copy.deepcopy(new_item)
					old_json['items'].append(old_item)
					old_items[key] = old_item
				else:
					for size, quantity in new_item['values'].items():
						old_item['values'][size] = (
							old_item['values'].get(size, 0) + quantity
						)
				old_item['total_qty'] = sum(old_item['values'].values())

			for size in new_json['total_qty']:
				old_json['total_qty'][size] = (
					old_json['total_qty'].get(size, 0) + new_json['total_qty'][size]
				)

			item_data[item_name]['completed_json'] = [old_json]

	return item_data

def get_lot_data(lot, lot_data, cloth_details, completed, item_name, lay_no, no_of_colours, version, total_qty):
	cloth_total = {
		"required": 0,
		"used": 0,
		"balance": 0,
		"received": 0,
	}
	if lot in lot_data:
		old_cloth_details = lot_data[lot]['cloth_details']
		for row1 in old_cloth_details:
			for row2 in cloth_details:
				if row1['cloth_item_variant'] == row2['cloth_item_variant']:
					row1['used_weight'] += row2['used_weight']
					row1['required_weight'] += row2['required_weight']
					row1['weight'] += row2['weight']

		for row1 in old_cloth_details:
			row1['balance_weight'] = round(row1['weight'] - row1['used_weight'], 3	)
			cloth_total['balance'] += row1['balance_weight']
			cloth_total['received'] += row1['weight']
			cloth_total['used'] += row1['used_weight']
			cloth_total['required'] += row1['required_weight']

		lot_data[lot]['cloth_total'] = cloth_total
		lot_data[lot]['cloth_details'] = old_cloth_details

		old_completed = lot_data[lot]['completed_json']
		for row1, row2 in zip(old_completed, completed):
			for item1, item2 in zip(row1['items'], row2['items']):
				for size1, size2 in zip(item1['values'], item2['values']):
					item1['values'][size1] += item2['values'][size2]
				item1['total_qty'] += item2['total_qty']
		lot_data[lot]['completed_json'] = old_completed
	else:
		for row in cloth_details:
			cloth_total['required'] += row['required_weight']
			cloth_total['used'] += row['used_weight']
			cloth_total['balance'] += row['balance_weight']
			cloth_total['received'] += row['weight']

		lot_data[lot] = {
			"item": item_name,
			"lay_no": lay_no,
			"no_of_colours": no_of_colours,
			"completed_json": completed,
			"version": version,
			"total_qty": total_qty,
			"cloth_details": cloth_details,
			"cloth_total": cloth_total,
		}
	return lot_data
