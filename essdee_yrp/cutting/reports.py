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
from frappe.utils import flt, getdate, sbool
from frappe.model import get_permitted_fields
from yrp import attribute_links as attribute_db
from yrp.attribute_links import value as _attribute_value

from essdee_yrp.ipd_attribute_links import major_stitching_value


def _require_report_access() -> None:
	"""Require the same read authority as the Cutting LaySheet data being reported."""

	frappe.has_permission("SD YRP Cutting LaySheet", ptype="read", throw=True)


def _accessible_laysheets(filters=None, fields=None):
	"""Return only LaySheets visible through record and User Permissions."""

	return frappe.get_list(
		"SD YRP Cutting LaySheet",
		filters=filters or {},
		fields=fields or ["name"],
		limit_page_length=0,
	)


def _can_read_doc(doc):
	return bool(frappe.has_permission(doc.doctype, ptype="read", doc=doc))


def _readable_plan_work_order(plan):
	"""Return a Work Order only when its protected link and record are readable."""

	try:
		read_fields = set(get_permitted_fields("SD YRP Cutting Plan", permission_type="read"))
	except TypeError:
		read_fields = set(get_permitted_fields("SD YRP Cutting Plan", "read"))
	work_order_name = getattr(plan, "work_order", None)
	if "work_order" not in read_fields or not work_order_name:
		return None
	work_order = frappe.get_doc("YRP Work Order", work_order_name)
	return work_order if _can_read_doc(work_order) else None


@frappe.whitelist()
def get_report_permissions():
	"""Return effective Frappe permissions used to expose Cutting workspaces."""

	can_read_cutting = bool(frappe.has_permission("SD YRP Cutting LaySheet", ptype="read"))
	can_read_stock = bool(
		frappe.has_permission("YRP Stock Ledger Entry", ptype="read")
		and frappe.has_permission("YRP Stock Ledger Entry", ptype="report")
	)
	return {
		"cutting-plans": bool(frappe.has_permission("SD YRP Cutting Plan", ptype="read")),
		"daily-production": can_read_cutting,
		"daily-cut-sheet": can_read_cutting,
		"multi-ccr": can_read_cutting,
		"cutting-detail": can_read_cutting,
		"stock-balance": can_read_stock,
	}


def update_if_string_instance(value):
	if isinstance(value, str):
		value = json.loads(value)

	return value or {}


def get_stich_details(ipd_doc):
	return {
		_attribute_value(row.stiching_attribute_value): _attribute_value(row.set_item_attribute_value)
		for row in ipd_doc.stiching_item_details
	}


def group_laysheet_stats_by_parent(cls_rows, report_date):
	"""Group lay sheets by their real parent.

	MariaDB can store the unused secondary parent as either NULL or an empty
	string. Grouping both parent columns in SQL consequently split a single
	Cutting Plan into duplicate report sections. Normalising in Python keeps
	the report stable for both old and new records.
	"""

	report_date = getdate(report_date)
	stats_by_parent = {}
	for row in cls_rows:
		if row.get("cutting_plan"):
			key = ("SD YRP Cutting Plan", row["cutting_plan"])
		elif row.get("cutting_order"):
			key = ("SD YRP Cutting Order", row["cutting_order"])
		else:
			continue

		stats = stats_by_parent.setdefault(
			key,
			{"names": [], "bundle_count": 0, "label_count": 0, "created_count": 0},
		)
		stats["names"].append(row["name"])
		stats["bundle_count"] += 1
		stats["label_count"] += int(row.get("status") == "Label Printed")
		stats["created_count"] += int(
			bool(row.get("posting_date")) and getdate(row["posting_date"]) == report_date
		)

	return stats_by_parent


def get_bundles_by_cutter(cls_list, bundles_by_parent):
	"""Group a parent's bundles by cutter while preserving lay-sheet identity."""

	bundles_by_cutter = {}
	for cls in cls_list:
		for bundle in bundles_by_parent.get(cls["name"], []):
			cutter = bundle.get("cutter") or ""
			bundles_by_cutter.setdefault(cutter, {}).setdefault(cls["name"], []).append(bundle)
	return bundles_by_cutter


@frappe.whitelist()
def get_daily_production_report(date, location, items=None, lots=None, only_label_printed=False):
	_require_report_access()
	from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant

	from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
		get_complete_incomplete_structure,
	)
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import fetch_order_item_details

	report_date = getdate(date)
	only_label_printed = sbool(only_label_printed)

	filters = {"bundle_generated_date": report_date}
	filters["status"] = "Label Printed" if only_label_printed else ["!=", "Cancelled"]
	cls_rows = _accessible_laysheets(
		filters,
		["name", "cutting_plan", "cutting_order", "status", "posting_date"],
	)
	if items or lots:
		filtered_rows = []
		for row in cls_rows:
			parent_dt = "SD YRP Cutting Plan" if row.get("cutting_plan") else "SD YRP Cutting Order"
			parent_name = row.get("cutting_plan") or row.get("cutting_order")
			if not parent_name:
				continue
			if parent_dt == "SD YRP Cutting Plan":
				parent_item, parent_lot = frappe.db.get_value(parent_dt, parent_name, ["item", "lot"]) or (None, None)
			else:
				parent_item = frappe.db.get_value(parent_dt, parent_name, "item")
				parent_lot = None
			if (items and parent_item in items) or (lots and parent_lot in lots):
				filtered_rows.append(row)
		cls_rows = filtered_rows

	if not cls_rows:
		return {"report_data": [], "bundle_generated": 0, "label_printed": 0, "created": 0}

	cls_stats_map = group_laysheet_stats_by_parent(cls_rows, report_date)

	# Step 2: Bulk-fetch all CLS bundle data
	all_cls_names = []
	for stat in cls_stats_map.values():
		all_cls_names.extend(stat["names"])

	bundles_by_parent = {}
	if all_cls_names:
		bundles = attribute_db.business_values(
			frappe.db.sql(
				"""
			SELECT bundle.parent, bundle.part, bundle.size, bundle.quantity,
				bundle.colour, bundle.set_combination, laysheet.cutter
			FROM `tabSD YRP Cutting LaySheet Bundle` bundle
			JOIN `tabSD YRP Cutting LaySheet` laysheet ON laysheet.name = bundle.parent
			WHERE bundle.parent IN %(names)s
		""",
				{"names": all_cls_names},
				as_dict=True,
			)
		)
		for b in bundles:
			bundles_by_parent.setdefault(b["parent"], []).append(b)

	# Step 3: Read planned quantities only through permitted Plan links and Work Orders.
	cp_names = [name for dt, name in cls_stats_map.keys() if dt == "SD YRP Cutting Plan"]
	wo_planned_by_cp = {}
	for cp_name in cp_names:
		cp_doc = frappe.get_doc("SD YRP Cutting Plan", cp_name)
		if not _can_read_doc(cp_doc):
			continue
		work_order = _readable_plan_work_order(cp_doc)
		if not work_order:
			continue
		for row in work_order.work_order_calculated_items:
			wo_planned_by_cp.setdefault(cp_name, {})[row.item_variant] = {
				"planned": row.quantity,
				"cumulative": row.received_qty,
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
		if parent_dt == "SD YRP Cutting Plan":
			cp_doc = frappe.get_doc("SD YRP Cutting Plan", parent_name)
			if not _can_read_doc(cp_doc):
				continue
			if cp_doc.version == "V1":
				frappe.throw("Can't get report for Cutting Plan Version V1")
			if location and cp_doc.cutting_location != location:
				continue
			detail_doc = frappe.get_cached_doc("YRP Item Production Detail", cp_doc.production_detail)
			item_details = fetch_order_item_details(cp_doc.items, cp_doc.production_detail)
			completed, incomplete = get_complete_incomplete_structure(cp_doc.production_detail, item_details)
			incomplete_items = update_if_string_instance(incomplete)
			completed_items = update_if_string_instance(completed)
			parent_item = cp_doc.item
			parent_lot = cp_doc.lot
			parent_location = cp_doc.cutting_location
			planned_dict = wo_planned_by_cp.get(parent_name, {})
		else:
			co_doc = frappe.get_doc("SD YRP Cutting Order", parent_name)
			if not _can_read_doc(co_doc):
				continue
			if location and co_doc.cutting_location != location:
				continue
			detail_doc = frappe.get_cached_doc("SD YRP Cutting Order Detail", co_doc.cutting_order_detail)
			completed_items = update_if_string_instance(co_doc.completed_items_json)
			incomplete_items = update_if_string_instance(co_doc.incomplete_items_json)
			# Enrich CO structure to match CP format expected by Vue template
			attr_list = [detail_doc.packing_attribute]
			if detail_doc.is_set_item and detail_doc.set_item_attribute:
				attr_list.append(detail_doc.set_item_attribute)
			completed_items.setdefault("attributes", attr_list)
			completed_items.setdefault("primary_attribute", detail_doc.primary_attribute)
			for item in completed_items.get("items", []):
				item.setdefault("is_set_item", detail_doc.is_set_item)
				item.setdefault("set_attr", detail_doc.set_item_attribute if detail_doc.is_set_item else None)
				item.setdefault("pack_attr", detail_doc.packing_attribute)
				item.setdefault("major_attr_value", None)
				item.setdefault("primary_attribute", detail_doc.primary_attribute)
				if item.get("item_keys") is None:
					colour = item.get("attributes", {}).get(detail_doc.packing_attribute, "")
					item["item_keys"] = {"major_colour": colour}
			parent_item = co_doc.item
			parent_lot = ""
			parent_location = co_doc.cutting_location
			planned_dict = {}

		bundle_generated += stats["bundle_count"]
		label_printed += stats["label_count"]
		created += stats["created_count"]

		cls_name_list = [{"name": n} for n in stats["names"]]
		bundles_by_cutter = get_bundles_by_cutter(cls_name_list, bundles_by_parent)

		major_panel = {}
		panel_qty = {}
		for row in detail_doc.stiching_item_details:
			if row.is_default:
				major_panel[_attribute_value(row.set_item_attribute_value)] = _attribute_value(
					row.stiching_attribute_value
				)
			panel_qty[_attribute_value(row.stiching_attribute_value)] = row.quantity

		if not detail_doc.is_set_item:
			if hasattr(detail_doc, "stiching_major_attribute_value") and major_stitching_value(detail_doc):
				major_panel["panel"] = major_stitching_value(detail_doc)
			else:
				# COD may not have stiching_major_attribute_value; derive from is_default or first panel
				for row in detail_doc.stiching_item_details:
					if row.is_default:
						major_panel["panel"] = _attribute_value(row.stiching_attribute_value)
						break
				if "panel" not in major_panel and detail_doc.stiching_item_details:
					major_panel["panel"] = _attribute_value(
						detail_doc.stiching_item_details[0].stiching_attribute_value
					)

		items_list = []
		total = 0
		total_planned_qty = 0
		total_received_qty = 0
		planned_rows_counted = set()
		report_items = copy.deepcopy(completed_items)

		for cutter, cutter_bundles in sorted(bundles_by_cutter.items()):
			cutter_completed, cutter_incomplete = calculate_completed(
				cls_name_list,
				detail_doc,
				copy.deepcopy(completed_items),
				copy.deepcopy(incomplete_items),
				cutter_bundles,
			)

			for row1, row2 in zip_longest(cutter_completed["items"], cutter_incomplete["items"]):
				row1["values1"] = {}
				if detail_doc.is_set_item:
					part = row1["attributes"][detail_doc.set_item_attribute]
					panel = major_panel[part]
					for size in row1["values"]:
						if row2["values"][size][panel] > 0:
							row1["values"][size] += row2["values"][size][panel]
							row1["values1"][size] = get_less_qty_panels(
								row2["values"][size], panel, panel_qty
							)
				else:
					panel = _attribute_value(major_panel["panel"])
					for size in row1["values"]:
						if row2["values"][size][panel] > 0:
							row1["values"][size] += row2["values"][size][panel]
							row1["values1"][size] = get_less_qty_panels(
								row2["values"][size], panel, panel_qty
							)

			for row in cutter_completed["items"]:
				total_qty = 0
				total_planned = 0
				total_received = 0
				planned_row_key = json.dumps(
					[row.get("attributes", {}), row.get("item_keys", {})],
					sort_keys=True,
					default=str,
				)
				row["cutter"] = cutter
				for val in row["values"]:
					if row["values"][val] <= 0:
						continue
					total_qty += row["values"][val]
					if planned_dict:
						attrs = row["attributes"].copy()
						attrs[row["primary_attribute"]] = val
						variant = cached_get_variant(parent_item, attrs)
						if variant in planned_dict:
							total_planned += planned_dict[variant]["planned"]
							total_received += planned_dict[variant]["cumulative"]

				if total_qty > 0:
					row["total_qty"] = total_qty
					row["planned"] = total_planned
					row["cumulative"] = total_received
					items_list.append(row)
					total += total_qty
					if planned_row_key not in planned_rows_counted:
						total_planned_qty += total_planned
						total_received_qty += total_received
						planned_rows_counted.add(planned_row_key)

		if len(items_list) == 0:
			continue
		else:
			report_items["items"] = items_list
			report_items["total_sum"] = total
			report_items["total_planned_sum"] = total_planned_qty
			report_items["total_received_sum"] = total_received_qty
			report_items["style_no"] = parent_item
			report_items["lot_no"] = parent_lot
			report_items["location"] = parent_location
			report.append(report_items)

	return {
		"report_data": report,
		"bundle_generated": bundle_generated,
		"label_printed": label_printed,
		"created": created,
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

	filters = [["status", "=", "Label Printed"], ["bundle_generated_date", "is", "set"]]
	if from_date:
		filters.append(["bundle_generated_date", ">=", getdate(from_date)])
	if to_date:
		filters.append(["bundle_generated_date", "<=", getdate(to_date)])
	rows = _accessible_laysheets(filters, ["bundle_generated_date", "item", "lot"])
	dates = sorted(
		{
			row["bundle_generated_date"]
			for row in rows
			if (not items_list and not lots_list)
			or (items_list and row.get("item") in items_list)
			or (lots_list and row.get("lot") in lots_list)
		},
		reverse=True,
	)

	result = []
	for d in dates:
		data = get_daily_production_report(
			str(d), location, items=items_list or None, lots=lots_list or None, only_label_printed=True
		)
		if items_list or lots_list:
			filtered = [
				entry
				for entry in data["report_data"]
				if entry.get("style_no") in items_list or entry.get("lot_no") in lots_list
			]
		else:
			filtered = data["report_data"]
		if filtered:
			result.append(
				{
					"date": str(d),
					"report_data": filtered,
					"bundle_generated": data["bundle_generated"],
					"label_printed": data["label_printed"],
					"created": data["created"],
				}
			)

	return result


@frappe.whitelist()
def get_cutting_detail_report(start_date, end_date, location):
	_require_report_access()
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
		get_complete_incomplete_structure,
	)
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import fetch_order_item_details

	generated_rows = _accessible_laysheets(
		[
			["bundle_generated_date", "between", [getdate(start_date), getdate(end_date)]],
			["status", "=", "Label Printed"],
		],
		["name", "cutting_plan"],
	)
	created_rows = _accessible_laysheets(
		[
			["posting_date", "between", [getdate(start_date), getdate(end_date)]],
			["status", "=", "Label Printed"],
		],
		["name", "cutting_plan"],
	)
	cutting_plans = [{"cutting_plan": name} for name in sorted({row.get("cutting_plan") for row in generated_rows if row.get("cutting_plan")})]
	report = []
	bundle_generated = 0
	label_printed = 0
	created = 0
	for cutting_plan in cutting_plans:
		cp_doc = frappe.get_doc("SD YRP Cutting Plan", cutting_plan["cutting_plan"])
		if not _can_read_doc(cp_doc):
			continue
		if cp_doc.version == "V1":
			frappe.throw("Can't get report for Cutting Plan Version V1")
		if location and cp_doc.cutting_location != location:
			continue
		item_details = fetch_order_item_details(cp_doc.items, cp_doc.production_detail)
		completed, incomplete = get_complete_incomplete_structure(cp_doc.production_detail, item_details)
		incomplete_items = update_if_string_instance(incomplete)
		completed_items = update_if_string_instance(completed)
		production_detail = cp_doc.production_detail
		ipd_doc = frappe.get_cached_doc("YRP Item Production Detail", production_detail)
		cls_list = [
			{"name": row["name"]}
			for row in generated_rows
			if row.get("cutting_plan") == cutting_plan["cutting_plan"]
		]
		bundle_generated += len(cls_list)
		cls_list2 = cls_list
		label_printed += len(cls_list2)
		cls_list3 = [row for row in created_rows if row.get("cutting_plan") == cutting_plan["cutting_plan"]]
		created += len(cls_list3)
		completed_items, incomplete_items = calculate_completed(
			cls_list, ipd_doc, completed_items, incomplete_items
		)
		major_panel = {}
		panel_qty = {}
		for row in ipd_doc.stiching_item_details:
			if row.is_default:
				major_panel[_attribute_value(row.set_item_attribute_value)] = _attribute_value(
					row.stiching_attribute_value
				)
			panel_qty[_attribute_value(row.stiching_attribute_value)] = row.quantity

		if not ipd_doc.is_set_item:
			major_panel["panel"] = major_stitching_value(ipd_doc)

		for row1, row2 in zip_longest(completed_items["items"], incomplete_items["items"]):
			row1["values1"] = {}
			if ipd_doc.is_set_item:
				part = row1["attributes"][ipd_doc.set_item_attribute]
				panel = major_panel[part]
				for size in row1["values"]:
					if row2["values"][size][panel] > 0:
						row1["values"][size] += row2["values"][size][panel]
						x = get_less_qty_panels(row2["values"][size], panel, panel_qty)
						row1["values1"][size] = x
			else:
				for size in row1["values"]:
					if row2["values"][size][_attribute_value(major_panel["panel"])] > 0:
						row1["values"][size] += row2["values"][size][_attribute_value(major_panel["panel"])]
						x = get_less_qty_panels(
							row2["values"][size], _attribute_value(major_panel["panel"]), panel_qty
						)
						row1["values1"][size] = x

		items_list = []
		total = 0
		total_planned_qty = 0
		total_received_qty = 0
		planned_dict = {}
		wo_doc = _readable_plan_work_order(cp_doc)
		if wo_doc:
			for row in wo_doc.work_order_calculated_items:
				planned_dict.setdefault(
					row.item_variant, {"planned": row.quantity, "cumulative": row.received_qty}
				)
		from yrp.yrp.doctype.yrp_item.yrp_item import get_or_create_variant

		for row in completed_items["items"]:
			total_qty = 0
			total_planned = 0
			total_received = 0
			for val in row["values"]:
				if row["values"][val] > 0:
					total_qty += row["values"][val]
					attrs = row["attributes"]
					attrs[row["primary_attribute"]] = val
					variant = get_or_create_variant(cp_doc.item, attrs)
					if planned_dict and variant in planned_dict:
						total_planned += planned_dict[variant]["planned"]
						total_received += planned_dict[variant]["cumulative"]

			if total_qty > 0:
				row["total_qty"] = total_qty
				row["planned"] = total_planned
				row["cumulative"] = total_received
				items_list.append(row)
				total += total_qty
				total_planned_qty += total_planned
				total_received_qty += total_received

		if len(items_list) == 0:
			continue
		else:
			completed_items["items"] = items_list
		completed_items["total_sum"] = total
		completed_items["total_planned_sum"] = total_planned_qty
		completed_items["total_received_sum"] = total_received_qty
		completed_items["style_no"] = cp_doc.item
		completed_items["lot_no"] = cp_doc.lot
		completed_items["location"] = cp_doc.cutting_location
		report.append(completed_items)

	return {
		"report_data": report,
		"bundle_generated": bundle_generated,
		"label_printed": label_printed,
		"created": created,
	}


def get_less_qty_panels(values, major_panel, panel_qty):
	result = []
	major_panel_qty = values[major_panel]
	for panel in values:
		if panel == major_panel:
			continue

		if panel_qty[major_panel] == panel_qty[panel]:
			if values[panel] < major_panel_qty:
				result.append({"panel": panel, "qty": major_panel_qty - values[panel]})
		elif panel_qty[major_panel] < panel_qty[panel]:
			diff = panel_qty[panel] - panel_qty[major_panel]
			qty = major_panel_qty
			while diff > 0:
				qty = qty + major_panel_qty
				diff = diff - 1
			if qty > values[panel]:
				result.append({"panel": panel, "qty": qty - values[panel]})

	return result


def calculate_completed(cls_list, ipd_doc, completed_items, incomplete_items, bundles_by_parent=None):
	for cls in cls_list:
		# Use pre-fetched bundle data if available, otherwise fall back to get_doc
		if bundles_by_parent is not None:
			cls_bundles = bundles_by_parent.get(cls["name"], [])
		else:
			cls_doc = frappe.get_doc("SD YRP Cutting LaySheet", cls["name"])
			cls_bundles = cls_doc.cutting_laysheet_bundles
		if not ipd_doc.is_set_item:
			alter_incomplete_items = {}
			for item in incomplete_items["items"]:
				colour = item["attributes"][ipd_doc.packing_attribute]
				alter_incomplete_items[colour] = item["values"]

			for item in cls_bundles:
				parts = _attribute_value(item.part).split(",")
				set_combination = update_if_string_instance(item.set_combination)
				set_colour = set_combination["major_colour"]
				qty = item.quantity
				for part in parts:
					alter_incomplete_items[set_colour][_attribute_value(item.size)][part] += qty
			total_qty = completed_items["total_qty"]
			for item in completed_items["items"]:
				colour = item["attributes"][ipd_doc.packing_attribute]
				for val in item["values"]:
					min = sys.maxsize
					if not alter_incomplete_items[colour].get(val):
						continue
					for panel in alter_incomplete_items[colour][val]:
						if alter_incomplete_items[colour][val][panel] < min:
							min = alter_incomplete_items[colour][val][panel]
					total_qty.setdefault(val, 0)
					total_qty[val] += min
					item["values"][val] += min
					for panel in alter_incomplete_items[colour][val]:
						alter_incomplete_items[colour][val][panel] -= min
			completed_items["total_qty"] = total_qty
			for item in incomplete_items["items"]:
				colour = item["attributes"][ipd_doc.packing_attribute]
				item["values"] = alter_incomplete_items[colour]
		else:
			stich_details = get_stich_details(ipd_doc)
			alter_incomplete_items = {}
			for item in incomplete_items["items"]:
				set_combination = update_if_string_instance(item["item_keys"])
				colour = set_combination["major_colour"]
				part = item["attributes"][ipd_doc.set_item_attribute]
				if alter_incomplete_items.get(colour):
					alter_incomplete_items[colour][part] = item["values"]
				else:
					alter_incomplete_items[colour] = {}
					alter_incomplete_items[colour][part] = item["values"]
			for item in cls_bundles:
				parts = _attribute_value(item.part).split(",")
				set_combination = update_if_string_instance(item.set_combination)
				major_part = set_combination["major_part"]
				major_colour = set_combination["major_colour"]
				d = {
					"major_colour": major_colour,
				}
				if set_combination.get("set_part"):
					major_part = set_combination["set_part"]
					major_colour = set_combination["set_colour"]
				d["major_part"] = major_part

				qty = item.quantity
				for part in parts:
					try:
						alter_incomplete_items[d["major_colour"]][d["major_part"]][
							_attribute_value(item.size)
						][part] += qty
					except KeyError, TypeError:
						secondary_part = stich_details[part]
						alter_incomplete_items[d["major_colour"]][secondary_part][
							_attribute_value(item.size)
						][part] += qty

			total_qty = completed_items["total_qty"]
			for item in completed_items["items"]:
				set_combination = update_if_string_instance(item["item_keys"])
				colour = set_combination["major_colour"]
				part = item["attributes"][ipd_doc.set_item_attribute]
				for val in item["values"]:
					min = sys.maxsize
					for panel in alter_incomplete_items[colour][part][val]:
						if alter_incomplete_items[colour][part][val][panel] < min:
							min = alter_incomplete_items[colour][part][val][panel]

					total_qty.setdefault(val, 0)
					total_qty[val] += min
					item["values"][val] += min
					for panel in alter_incomplete_items[colour][part][val]:
						alter_incomplete_items[colour][part][val][panel] -= min

			completed_items["total_qty"] = total_qty
			for item in incomplete_items["items"]:
				set_combination = update_if_string_instance(item["item_keys"])
				colour = set_combination["major_colour"]
				part = item["attributes"][ipd_doc.set_item_attribute]
				item["values"] = alter_incomplete_items[colour][part]

	return completed_items, incomplete_items


@frappe.whitelist()
def get_cut_sheet_report(date, location):
	_require_report_access()
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
		get_complete_incomplete_structure,
	)
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import fetch_order_item_details

	report_date = getdate(date)

	accessible_rows = _accessible_laysheets(
		{"bundle_generated_date": report_date},
		["name", "cutting_plan", "cutting_order"],
	)
	parent_rows = [
		{"cutting_plan": cutting_plan, "cutting_order": cutting_order}
		for cutting_plan, cutting_order in sorted(
			{(row.get("cutting_plan") or "", row.get("cutting_order") or "") for row in accessible_rows}
		)
	]

	report = []
	for parent_row in parent_rows:
		if parent_row["cutting_plan"]:
			parent_name = parent_row["cutting_plan"]
			cp_doc = frappe.get_doc("SD YRP Cutting Plan", parent_name)
			if not _can_read_doc(cp_doc):
				continue
			if cp_doc.version == "V1":
				frappe.throw("Can't get report for Cutting Plan Version V1")
			if location and cp_doc.cutting_location != location:
				continue
			item_details = fetch_order_item_details(cp_doc.items, cp_doc.production_detail)
			_completed, incomplete = get_complete_incomplete_structure(cp_doc.production_detail, item_details)
			incomplete_items = update_if_string_instance(incomplete)
			detail_doc = frappe.get_cached_doc("YRP Item Production Detail", cp_doc.production_detail)
			parent_item = cp_doc.item
			parent_lot = cp_doc.lot
			parent_location = cp_doc.cutting_location
			parent_field = "cutting_plan"
		elif parent_row["cutting_order"]:
			parent_name = parent_row["cutting_order"]
			co_doc = frappe.get_doc("SD YRP Cutting Order", parent_name)
			if not _can_read_doc(co_doc):
				continue
			if location and co_doc.cutting_location != location:
				continue
			incomplete_items = update_if_string_instance(co_doc.incomplete_items_json)
			detail_doc = frappe.get_cached_doc("SD YRP Cutting Order Detail", co_doc.cutting_order_detail)
			# Enrich CO structure to match CP format expected by Vue template
			attr_list = [detail_doc.packing_attribute]
			if detail_doc.is_set_item and detail_doc.set_item_attribute:
				attr_list.append(detail_doc.set_item_attribute)
			incomplete_items.setdefault("attributes", attr_list)
			incomplete_items.setdefault("primary_attribute", detail_doc.primary_attribute)
			for item in incomplete_items.get("items", []):
				item.setdefault("is_set_item", detail_doc.is_set_item)
				item.setdefault("set_attr", detail_doc.set_item_attribute if detail_doc.is_set_item else None)
				item.setdefault("pack_attr", detail_doc.packing_attribute)
				item.setdefault("major_attr_value", None)
				item.setdefault("primary_attribute", detail_doc.primary_attribute)
				if item.get("item_keys") is None:
					colour = item.get("attributes", {}).get(detail_doc.packing_attribute, "")
					item["item_keys"] = {"major_colour": colour}
			parent_item = co_doc.item
			parent_lot = ""
			parent_location = co_doc.cutting_location
			parent_field = "cutting_order"
		else:
			continue

		cls_list = [
			{"name": row["name"]}
			for row in accessible_rows
			if row.get(parent_field) == parent_name
		]

		cls_docs_by_cutter = {}
		for cls in cls_list:
			cls_doc = frappe.get_doc("SD YRP Cutting LaySheet", cls["name"])
			cls_docs_by_cutter.setdefault(cls_doc.cutter or "", []).append(cls_doc)

		items_list = []
		for cutter, cls_docs in sorted(cls_docs_by_cutter.items()):
			cutter_items = copy.deepcopy(incomplete_items)
			alter_incomplete_items = {}
			if not detail_doc.is_set_item:
				for item in cutter_items["items"]:
					colour = item["attributes"][detail_doc.packing_attribute]
					alter_incomplete_items[colour] = item["values"]
			else:
				for item in cutter_items["items"]:
					set_combination = update_if_string_instance(item["item_keys"])
					colour = set_combination["major_colour"]
					part = item["attributes"][detail_doc.set_item_attribute]
					alter_incomplete_items.setdefault(colour, {})[part] = item["values"]

			for cls_doc in cls_docs:
				if not detail_doc.is_set_item:
					for item in cls_doc.cutting_laysheet_bundles:
						parts = _attribute_value(item.part).split(",")
						set_combination = update_if_string_instance(item.set_combination)
						set_colour = set_combination["major_colour"]
						for part in parts:
							alter_incomplete_items[set_colour][_attribute_value(item.size)][part] += item.quantity
				else:
					stich_details = get_stich_details(detail_doc)
					for item in cls_doc.cutting_laysheet_bundles:
						parts = _attribute_value(item.part).split(",")
						set_combination = update_if_string_instance(item.set_combination)
						major_part = set_combination["major_part"]
						major_colour = set_combination["major_colour"]
						if set_combination.get("set_part"):
							major_part = set_combination["set_part"]
							major_colour = set_combination["set_colour"]

						for part in parts:
							try:
								alter_incomplete_items[major_colour][major_part][
									_attribute_value(item.size)
								][part] += item.quantity
							except (KeyError, TypeError):
								secondary_part = stich_details[part]
								alter_incomplete_items[major_colour][secondary_part][
									_attribute_value(item.size)
								][part] += item.quantity

			if not detail_doc.is_set_item:
				for item in cutter_items["items"]:
					colour = item["attributes"][detail_doc.packing_attribute]
					item["values"] = alter_incomplete_items[colour]
			else:
				for item in cutter_items["items"]:
					set_combination = update_if_string_instance(item["item_keys"])
					colour = set_combination["major_colour"]
					part = item["attributes"][detail_doc.set_item_attribute]
					item["values"] = alter_incomplete_items[colour][part]

			for item in cutter_items["items"]:
				item["cutter"] = cutter
				item["total_panel_qty"] = {}
				add_item = False
				for size in item["values"]:
					for panel in item["values"][size]:
						if item["values"][size][panel] > 0:
							add_item = True
							item["total_panel_qty"].setdefault(panel, 0)
							item["total_panel_qty"][panel] += item["values"][size][panel]
				if add_item:
					items_list.append(item)

		if len(items_list) == 0:
			continue

		report_items = copy.deepcopy(incomplete_items)
		report_items["items"] = items_list
		report_items["style_no"] = parent_item
		report_items["lot_no"] = parent_lot
		report_items["location"] = parent_location
		report.append(report_items)

	return report


@frappe.whitelist()
def get_multiccr(open_status=None, lot_list=None, item_list=None, category=None):
	_require_report_access()
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
		get_ccr,
		get_recut_print_panel_details,
	)

	lot_list = update_if_string_instance(lot_list)
	item_list = update_if_string_instance(item_list)
	lot_filters = {"production_detail": ["is", "set"]}
	if lot_list:
		lot_filters["name"] = ["in", list(lot_list)]
	if item_list:
		lot_filters["item"] = ["in", list(item_list)]
	if open_status:
		lot_filters["status"] = open_status
	lot_rows = frappe.get_list(
		"SD YRP Lot",
		filters=lot_filters,
		fields=["name", "item"],
		limit_page_length=0,
	)
	if category:
		lot_rows = [
			row
			for row in lot_rows
			if frappe.db.get_value("Item", row.get("item"), "product_category") == category
		]
	lot_data = {}
	output_lots = []
	output_items = []
	for lot in lot_rows:
		lot = lot["name"]
		cp_list = frappe.get_list(
			"SD YRP Cutting Plan",
			filters={
				"lot": lot,
				"docstatus": 1,
			},
			pluck="name",
			limit_page_length=0,
		)
		total_qty = 0
		panel_groups = []
		recut_rows = {}
		for cp in cp_list:
			if lot not in output_lots:
				output_lots.append(lot)
			cp_fields = [
				"item",
				"lay_no",
				"no_of_colours",
				"completed_items_json",
				"version",
				"production_detail",
			]
			(
				item_name,
				lay_no,
				no_of_colours,
				completed,
				version,
				production_detail,
			) = frappe.get_value("SD YRP Cutting Plan", cp, cp_fields)
			if item_name not in output_items:
				output_items.append(item_name)
			completed = [update_if_string_instance(completed)]
			for row in completed:
				if not row["is_set_item"]:
					for item in row["items"]:
						total = 0
						for size in item["values"]:
							total += item["values"][size]
						item["total_qty"] = total
						total_qty += total
				else:
					set_attribute = row.get("set_item_attr") or attribute_db.get_cached_value(
						"YRP Item Production Detail",
						production_detail,
						"set_item_attribute",
					)
					for part in row["Panel"]:
						for item in row["items"]:
							if item["attributes"][set_attribute] == part:
								total = 0
								for size in item["values"]:
									total += item["values"][size]
								item["total_qty"] = total
								total_qty += total
			cloth_details = attribute_db.get_all(
				"SD YRP Cutting Plan Cloth Detail",
				filters={
					"parent": cp,
					"parenttype": "SD YRP Cutting Plan",
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
				lot, lot_data, cloth_details, completed, item_name, lay_no, no_of_colours, version, total_qty
			)
			ccr_data = get_ccr(cp)
			panel_groups.extend(serialize_multiccr_panel_groups(cp, ccr_data))
			recut_details = (
				ccr_data.get("recut_details")
				if ccr_data
				else get_recut_print_panel_details(cp, "Recut")
			)
			merge_multiccr_recut_rows(recut_rows, recut_details)

		if lot in lot_data:
			lot_data[lot]["panel_groups"] = panel_groups
			lot_data[lot]["recut_summary"] = serialize_multiccr_recut_summary(recut_rows)

	item_data = get_item_data(lot_data)

	d = {
		"output_lots": output_lots,
		"output_items": output_items,
		"data": lot_data,
		"item_data": item_data,
	}
	return d


def serialize_multiccr_panel_groups(cutting_plan, ccr_data):
	"""Convert CCR marker data into JSON-safe, frontend-ready table groups."""

	if not ccr_data or not ccr_data.get("marker_data"):
		return []

	sizes = ccr_data.get("sizes") or []
	panel_groups = []
	for panels, marker_rows in ccr_data["marker_data"].items():
		rows = []
		totals = {
			"received_weight": 0,
			"used_weight": 0,
			"balance_weight": 0,
			"total_pieces": 0,
			"required_weight": 0,
			"sizes": {size: 0 for size in sizes},
		}

		for (colour, cloth_type), marker_row in marker_rows.items():
			total_pieces = flt(marker_row.get("total_pieces"))
			used_weight = flt(marker_row.get("used_weight"))
			required_weight = flt(marker_row.get("reqd_weight"))
			size_values = {
				size: flt((marker_row.get(size) or {}).get("bits")) for size in sizes
			}
			rows.append(
				{
					"colour": colour,
					"cloth_type": cloth_type,
					"received_weight": flt(marker_row.get("received_weight")),
					"used_weight": used_weight,
					"balance_weight": flt(marker_row.get("balance_weight")),
					"sizes": size_values,
					"total_pieces": total_pieces,
					"piece_weight": used_weight / total_pieces if total_pieces else 0,
					"required_weight": required_weight,
				}
			)

			totals["received_weight"] += flt(marker_row.get("received_weight"))
			totals["used_weight"] += used_weight
			totals["balance_weight"] += flt(marker_row.get("balance_weight"))
			totals["total_pieces"] += total_pieces
			totals["required_weight"] += required_weight
			for size in sizes:
				totals["sizes"][size] += size_values[size]

		if not rows:
			continue
		totals["piece_weight"] = (
			totals["used_weight"] / totals["total_pieces"] if totals["total_pieces"] else 0
		)
		totals["required_weight"] /= len(rows)
		panel_groups.append(
			{
				"cutting_plan": cutting_plan,
				"panels": panels,
				"sizes": sizes,
				"rows": rows,
				"totals": totals,
			}
		)

	return panel_groups


def merge_multiccr_recut_rows(target, recut_details):
	"""Merge Cutting Plan recut rows into a lot-wise summary."""

	for row in (recut_details or {}).values():
		key = (row.get("cloth_type"), row.get("colour"), row.get("dia"), row.get("shade"))
		target.setdefault(
			key,
			{
				"cloth_type": row.get("cloth_type"),
				"colour": row.get("colour"),
				"dia": row.get("dia"),
				"shade": row.get("shade"),
				"weight": 0,
				"no_of_rolls": 0,
			},
		)
		target[key]["weight"] += flt(row.get("weight"))
		target[key]["no_of_rolls"] += flt(row.get("no_of_rolls"))


def serialize_multiccr_recut_summary(recut_rows):
	rows = list(recut_rows.values())
	return {
		"rows": rows,
		"totals": {
			"weight": sum(row["weight"] for row in rows),
			"no_of_rolls": sum(row["no_of_rolls"] for row in rows),
		},
	}


def get_item_data(lot_data):
	item_data = {}
	lot_details = copy.deepcopy(lot_data)
	for lot in lot_details:
		item_name = lot_details[lot]["item"]
		if item_name not in item_data:
			item_data[item_name] = {
				"completed_json": lot_details[lot]["completed_json"],
				"total_qty": lot_details[lot]["total_qty"],
				"cloth_details": lot_details[lot]["cloth_details"],
				"cloth_total": lot_details[lot]["cloth_total"],
				"piece_weight_by_colour": {},
				"required_weight_by_colour": {},
			}
		else:
			item_data[item_name]["total_qty"] += lot_details[lot]["total_qty"]
			d = {}
			old_details = item_data[item_name]["cloth_details"]
			for row in old_details:
				key = (row["cloth_item_variant"], row["cloth_type"])
				d[key] = row

			for row in lot_details[lot]["cloth_details"]:
				key = (row["cloth_item_variant"], row["cloth_type"])
				if key in d:
					d[key]["used_weight"] += row["used_weight"]
					d[key]["weight"] += row["weight"]
					d[key]["required_weight"] += row["required_weight"]
				else:
					d[key] = row
			item_data[item_name]["cloth_total"]["balance"] = 0
			item_data[item_name]["cloth_total"]["received"] = 0
			item_data[item_name]["cloth_total"]["used"] = 0
			item_data[item_name]["cloth_total"]["required"] = 0
			for key in d:
				row = d[key]
				row["balance_weight"] = round(row["weight"] - row["used_weight"], 3)
				item_data[item_name]["cloth_total"]["balance"] += row["balance_weight"]
				item_data[item_name]["cloth_total"]["received"] += row["weight"]
				item_data[item_name]["cloth_total"]["used"] += row["used_weight"]
				item_data[item_name]["cloth_total"]["required"] += row["required_weight"]

			item_data[item_name]["cloth_details"] = list(d.values())

			old_json = item_data[item_name]["completed_json"][0]
			new_json = lot_details[lot]["completed_json"][0]
			old_items = {
				(
					json.dumps(item.get("attributes") or {}, sort_keys=True),
					json.dumps(item.get("item_keys") or {}, sort_keys=True),
				): item
				for item in old_json["items"]
			}
			for new_item in new_json["items"]:
				key = (
					json.dumps(new_item.get("attributes") or {}, sort_keys=True),
					json.dumps(new_item.get("item_keys") or {}, sort_keys=True),
				)
				old_item = old_items.get(key)
				if old_item is None:
					old_item = copy.deepcopy(new_item)
					old_json["items"].append(old_item)
					old_items[key] = old_item
				else:
					for size, quantity in new_item["values"].items():
						old_item["values"][size] = old_item["values"].get(size, 0) + quantity
				old_item["total_qty"] = sum(old_item["values"].values())

			for size in new_json["total_qty"]:
				old_json["total_qty"][size] = old_json["total_qty"].get(size, 0) + new_json["total_qty"][size]

			item_data[item_name]["completed_json"] = [old_json]

		for group in lot_details[lot].get("panel_groups") or []:
			for row in group.get("rows") or []:
				colour = row.get("colour")
				if not colour:
					continue
				colour_totals = item_data[item_name]["piece_weight_by_colour"].setdefault(
					colour, {"used_weight": 0, "total_pieces": 0}
				)
				colour_totals["used_weight"] += flt(row.get("used_weight"))
				colour_totals["total_pieces"] += flt(row.get("total_pieces"))

				required_weight = flt(row.get("required_weight"))
				total_pieces = flt(row.get("total_pieces"))
				if required_weight and total_pieces:
					required_totals = item_data[item_name]["required_weight_by_colour"].setdefault(
						colour, {"weighted_weight": 0, "total_pieces": 0}
					)
					required_totals["weighted_weight"] += required_weight * total_pieces
					required_totals["total_pieces"] += total_pieces

	for item in item_data.values():
		item["average_piece_weight_by_colour"] = {
			colour: totals["used_weight"] / totals["total_pieces"]
			for colour, totals in item.pop("piece_weight_by_colour").items()
			if totals["total_pieces"]
		}
		item["average_required_weight_by_colour"] = {
			colour: totals["weighted_weight"] / totals["total_pieces"]
			for colour, totals in item.pop("required_weight_by_colour").items()
			if totals["total_pieces"]
		}

	return item_data


def get_lot_data(
	lot, lot_data, cloth_details, completed, item_name, lay_no, no_of_colours, version, total_qty
):
	cloth_total = {
		"required": 0,
		"used": 0,
		"balance": 0,
		"received": 0,
	}
	if lot in lot_data:
		old_cloth_details = lot_data[lot]["cloth_details"]
		for row1 in old_cloth_details:
			for row2 in cloth_details:
				if row1["cloth_item_variant"] == row2["cloth_item_variant"]:
					row1["used_weight"] += row2["used_weight"]
					row1["required_weight"] += row2["required_weight"]
					row1["weight"] += row2["weight"]

		for row1 in old_cloth_details:
			row1["balance_weight"] = round(row1["weight"] - row1["used_weight"], 3)
			cloth_total["balance"] += row1["balance_weight"]
			cloth_total["received"] += row1["weight"]
			cloth_total["used"] += row1["used_weight"]
			cloth_total["required"] += row1["required_weight"]

		lot_data[lot]["cloth_total"] = cloth_total
		lot_data[lot]["cloth_details"] = old_cloth_details

		old_completed = lot_data[lot]["completed_json"]
		for row1, row2 in zip(old_completed, completed, strict=False):
			for item1, item2 in zip(row1["items"], row2["items"], strict=False):
				for size1, size2 in zip(item1["values"], item2["values"], strict=False):
					item1["values"][size1] += item2["values"][size2]
				item1["total_qty"] += item2["total_qty"]
		lot_data[lot]["completed_json"] = old_completed
	else:
		for row in cloth_details:
			cloth_total["required"] += row["required_weight"]
			cloth_total["used"] += row["used_weight"]
			cloth_total["balance"] += row["balance_weight"]
			cloth_total["received"] += row["weight"]

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
