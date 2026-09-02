"""Permission-aware Sewing Plan read models and operator updates."""

from __future__ import annotations

from collections import defaultdict
import re

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt, getdate, today

from yrp.utils import get_variant_attr_details, update_if_string_instance
from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import (
	get_ipd_primary_values,
)

from essdee_yrp.sewing.entry import _entry_bucket, _variant_attributes
from essdee_yrp.sewing.entry import get_data_entry_data
from essdee_yrp.sewing.config import get_sewing_input_configuration


def _plans(supplier, *, lots=None, items=None):
	supplier = cstr(supplier).strip()
	if not supplier:
		frappe.throw(_("Sewing Unit is required."))
	frappe.has_permission('SD YRP Sewing Plan', "read", throw=True)
	filters = {"supplier": supplier}
	if lots:
		filters["lot"] = ["in", list(lots)]
	if items:
		filters["item"] = ["in", list(items)]
	return frappe.get_list(
		'SD YRP Sewing Plan',
		filters=filters,
		fields=["name", "lot", "item", "supplier", "work_order"],
		limit_page_length=0,
	)


def _entries(plans, *, entry_date=None, work_station=None, input_type=None):
	if not plans:
		return []
	frappe.has_permission('SD YRP Sewing Plan Entry Detail', "read", throw=True)
	filters = {"sewing_plan": ["in", [row.name for row in plans]]}
	if entry_date:
		filters["entry_date"] = getdate(entry_date)
	if work_station:
		filters["work_station"] = work_station
	if input_type:
		filters["input_type"] = input_type
	return frappe.get_list(
		'SD YRP Sewing Plan Entry Detail',
		filters=filters,
		fields=[
			"name",
			"sewing_plan",
			"input_type",
			"received_type",
			"work_station",
			"entry_date",
			"entry_time",
		],
		order_by="entry_date desc, entry_time desc, creation desc",
		limit_page_length=0,
	)


def _details(entries):
	if not entries:
		return []
	return frappe.get_all(
		'SD YRP Sewing Plan Detail',
		filters={
			"parent": ["in", [row.name for row in entries]],
			"parenttype": 'SD YRP Sewing Plan Entry Detail',
		},
		fields=["parent", "item_variant", "set_combination", "quantity"],
		limit_page_length=0,
	)


def _metadata(plans):
	lots = {
		row.name: row
		for row in frappe.get_all(
			'SD YRP Lot',
			filters={"name": ["in", list({row.lot for row in plans if row.lot})]},
			fields=["name", "item", "production_detail"],
			limit_page_length=0,
		)
	}
	ipd_names = {row.production_detail for row in lots.values() if row.production_detail}
	ipds = {
		row.name: row
		for row in frappe.get_all(
			'YRP Item Production Detail',
			filters={"name": ["in", list(ipd_names)]},
			fields=[
				"name",
				"item",
				"is_set_item",
				"packing_attribute",
				"primary_item_attribute",
				"set_item_attribute",
				"stiching_process",
			],
			limit_page_length=0,
		)
	}
	return lots, ipds


def _input_types(observed=None):
	result = [row.input_type for row in get_sewing_input_configuration()]
	for value in observed or []:
		if value and value not in result:
			result.append(value)
	return result


def _bucket(row, ipd, attributes):
	value, size = _entry_bucket(row, ipd, attributes)
	return value, size or "-"


@frappe.whitelist()
def get_dashboard_data(supplier):
	plans = _plans(supplier)
	entries = _entries(plans)
	details = _details(entries)
	entry_map = {row.name: row for row in entries}
	open_work_orders = set(
		frappe.get_all(
			'YRP Work Order',
			filters={
				"name": ["in", [row.work_order for row in plans if row.work_order]],
				"open_status": "Open",
			},
			pluck="name",
		)
	)
	plan_map = {row.name: row for row in plans}
	totals = defaultdict(float)
	for row in details:
		entry = entry_map.get(row.parent)
		plan = plan_map.get(entry.sewing_plan) if entry else None
		if plan and plan.work_order in open_work_orders:
			totals[entry.input_type] += flt(row.quantity)
	return [
		{"input_type": input_type, "qty": quantity}
		for input_type, quantity in sorted(
			totals.items(), key=lambda value: (-value[1], value[0])
		)
	]


@frappe.whitelist()
def get_sp_status_summary(supplier):
	"""Return the live, raw Sewing stage matrix for open Work Orders.

	F15 also calculated configured balance/status columns from the omitted
	``sewing_plan_input_orders`` rows. F16 deliberately exposes persisted facts
	only: ordered, each installed input type, and inspection quantities.
	"""

	payload = get_data_entry_data(supplier)
	headers = ["Order Qty", *payload.get("input_types", []), "Pre Final", "Final Inspection"]
	data = []
	totals = {header: 0 for header in headers}
	for lot, plans in (payload.get("data") or {}).items():
		for plan_name, plan in plans.items():
			details = plan.get("details") or {}
			if details.get("work_order_status") != "Open":
				continue
			for colour in (plan.get("colours") or {}).values():
				row = {
					"item": details.get("item"),
					"lot": lot,
					"sewing_plan": plan_name,
					"colour": colour.get("colour"),
					"part": colour.get("part"),
					"work_order_status": details.get("work_order_status"),
				}
				for header in headers:
					key = header.lower().replace(" ", "_")
					if header == "Pre Final":
						value = colour.get("inspection_total", {}).get("pre_final")
					elif header == "Final Inspection":
						value = colour.get("inspection_total", {}).get("final_inspection")
					else:
						value = sum(
							flt(size_values.get(key))
							for size_values in (colour.get("values") or {}).values()
						)
					row[header] = flt(value)
					totals[header] += flt(value)
				data.append(row)
	return {
		"header1": ['YRP Item', 'SD YRP Lot', "Colour", "Part"],
		"header2": headers,
		"header3": ["Work Order Status"],
		"data": [totals, *data] if data else [],
		"derived_balances_omitted": True,
	}


@frappe.whitelist()
def get_scr_data(supplier, lot):
	plans = _plans(supplier, lots=[lot])
	if not plans:
		return {
			"status": "failed",
			"message": _("No Sewing Plan found for this Sewing Unit and Lot."),
			"data": {},
		}
	plan_map = {row.name: row for row in plans}
	lots, ipds = _metadata(plans)
	lot_doc = lots.get(lot)
	ipd = ipds.get(lot_doc.production_detail) if lot_doc else None
	if not ipd:
		return {"status": "failed", "message": _("Lot has no production detail."), "data": {}}

	order_rows = frappe.get_all(
		'SD YRP Sewing Plan Order Detail',
		filters={"parent": ["in", list(plan_map)]},
		fields=["parent", "item_variant", "set_combination", "quantity", "pre_final", "final_inspection"],
		limit_page_length=0,
	)
	entries = _entries(plans)
	detail_rows = _details(entries)
	entry_map = {row.name: row for row in entries}
	work_order_names = [row.work_order for row in plans if row.work_order]
	delivered_rows = frappe.get_all(
		'YRP Work Order Calculated Item',
		filters={"parent": ["in", work_order_names]},
		fields=["parent", "item_variant", "set_combination", "delivered_quantity"],
		limit_page_length=0,
	) if work_order_names else []
	attributes = _variant_attributes(
		{
			row.item_variant
			for row in [*order_rows, *detail_rows, *delivered_rows]
			if row.item_variant
		}
	)
	data = {}
	colours = []
	lines = defaultdict(set)
	observed_headers = []

	def add(row, header, quantity, work_station=None):
		bucket, size = _bucket(row, ipd, attributes)
		colour = bucket["key"]
		if colour not in colours:
			colours.append(colour)
		group = data.setdefault(
			colour,
			{
				"values": {},
				"part": bucket["part"],
				"colour": colour,
				"variant_colour": bucket["variant_colour"],
				"set_combination": bucket["set_combination"],
				"type_wise_total": {},
			},
		)
		group["values"].setdefault(size, {})[header] = flt(
			group["values"].get(size, {}).get(header)
		) + flt(quantity)
		if work_station and re.match(r"sewing line\s+\d", cstr(work_station).strip(), re.I):
			lines[colour].add(work_station)
		if header not in observed_headers:
			observed_headers.append(header)

	for row in order_rows:
		add(row, "Order Qty", row.quantity)
		add(row, "Pre Final", row.pre_final)
		add(row, "Final Inspection", row.final_inspection)
	for row in delivered_rows:
		add(row, "Delivered Qty", row.delivered_quantity)
	default_received_type = frappe.db.get_single_value('YRP YRP Stock Settings', "default_received_type")
	for row in detail_rows:
		entry = entry_map[row.parent]
		header = entry.input_type
		if entry.received_type and entry.received_type != default_received_type:
			header = f"{header} {entry.received_type}"
		add(row, header, row.quantity, entry.work_station)

	preferred = ["Order Qty", "Delivered Qty", *_input_types(), "Pre Final", "Final Inspection"]
	headers = [header for header in preferred if header in observed_headers]
	headers.extend(header for header in observed_headers if header not in headers)
	for colour, group in data.items():
		group["lines"] = sorted(lines[colour], key=_natural_name_key)
		for header in headers:
			group["type_wise_total"][header] = sum(
				flt(values.get(header)) for values in group["values"].values()
			)
	return {
		"status": "success",
		"primary_values": get_ipd_primary_values(ipd.name),
		"data": data,
		"colours": colours,
		"headers": headers,
		"is_set_item": ipd.is_set_item,
		"set_attr": ipd.set_item_attribute,
		"item": plan_map[next(iter(plan_map))].item,
		"derived_balances_omitted": True,
	}


def _natural_name_key(value):
	match = re.search(r"\d+", cstr(value))
	return (cint(match.group()) if match else 10**9, cstr(value))


@frappe.whitelist()
def get_sewing_plan_entries(
	supplier, input_type=None, work_station=None, lot_name=None
):
	plans = _plans(supplier, lots=[lot_name] if lot_name else None)
	entries = _entries(plans, work_station=work_station, input_type=input_type)
	detail_rows = _details(entries)
	plan_map = {row.name: row for row in plans}
	lots, ipds = _metadata(plans)
	attributes = _variant_attributes({row.item_variant for row in detail_rows})
	by_entry = defaultdict(list)
	for row in detail_rows:
		by_entry[row.parent].append(row)
	previous_days = cint(
		frappe.db.get_single_value('SD YRP MRP Settings', "previous_day_entries")
	)
	cancellable_dates = {
		row.entry_date
		for row in frappe.db.sql(
			"""
				select entry.entry_date
				from `tabSD YRP Sewing Plan Entry Detail` entry
				join `tabSD YRP Sewing Plan` plan on plan.name = entry.sewing_plan
				where plan.supplier = %s
				group by entry.entry_date
				order by entry.entry_date desc
				limit %s
			""",
			(supplier, previous_days),
			as_dict=True,
		)
	} if previous_days else set()

	result = {}
	for entry in entries:
		plan = plan_map.get(entry.sewing_plan)
		lot = lots.get(plan.lot) if plan else None
		ipd = ipds.get(lot.production_detail) if lot else None
		if not plan or not ipd:
			continue
		value = {
			"lot": plan.lot,
			"details": {},
			"work_station": entry.work_station,
			"input_type": entry.input_type,
			"received_type": entry.received_type,
			"item_name": plan.item,
			"primary_values": get_ipd_primary_values(ipd.name),
			"is_set_item": ipd.is_set_item,
			"pack_attr": ipd.packing_attribute,
			"set_attr": ipd.set_item_attribute,
			"is_cancellable": bool(
				entry.entry_date in cancellable_dates
				and
				frappe.has_permission(
					'SD YRP Sewing Plan Entry Detail', "delete", doc=entry.name
				)
			),
			"entry_date": entry.entry_date,
			"entry_time": entry.entry_time,
		}
		for row in by_entry.get(entry.name, []):
			bucket, size = _bucket(row, ipd, attributes)
			colour = bucket["key"]
			group = value["details"].setdefault(
				colour,
				{
					"values": {},
					"part": bucket["part"],
					"colour": colour,
					"variant_colour": bucket["variant_colour"],
					"set_combination": bucket["set_combination"],
					"total": 0,
				},
			)
			group["values"][size] = flt(group["values"].get(size)) + flt(
				row.quantity
			)
			group["total"] += flt(row.quantity)
		result[entry.name] = value
	return result


@frappe.whitelist()
def get_sewing_plan_dpr_data(
	supplier, dpr_date, work_station=None, input_type=None
):
	plans = _plans(supplier)
	entries = _entries(
		plans,
		entry_date=dpr_date,
		work_station=work_station,
		input_type=input_type,
	)
	detail_rows = _details(entries)
	plan_map = {row.name: row for row in plans}
	entry_map = {row.name: row for row in entries}
	lots, ipds = _metadata(plans)
	attributes = _variant_attributes({row.item_variant for row in detail_rows})
	dpr_data = {}

	for row in detail_rows:
		entry = entry_map[row.parent]
		plan = plan_map.get(entry.sewing_plan)
		lot = lots.get(plan.lot) if plan else None
		ipd = ipds.get(lot.production_detail) if lot else None
		if not plan or not ipd:
			continue
		bucket, size = _bucket(row, ipd, attributes)
		lot_data = dpr_data.setdefault(entry.input_type, {}).setdefault(
			plan.lot,
			{
				"details": {},
				"is_set_item": ipd.is_set_item,
				"pack_attr": ipd.packing_attribute,
				"set_attr": ipd.set_item_attribute,
				"item": plan.item,
				"primary_values": get_ipd_primary_values(ipd.name),
			},
		)
		group = (
			lot_data["details"]
			.setdefault(entry.work_station or "-", {})
			.setdefault(entry.received_type or "-", {})
			.setdefault(
				bucket["key"],
				{
					"values": {},
					"part": bucket["part"],
					"colour": bucket["key"],
					"variant_colour": bucket["variant_colour"],
					"set_combination": bucket["set_combination"],
					"total": 0,
				},
			)
		)
		group["values"][size] = flt(group["values"].get(size)) + flt(row.quantity)
		group["total"] += flt(row.quantity)

	entry_plan_names = {row.sewing_plan for row in entries}
	pending_fi = []
	seen = set()
	if entry_plan_names:
		order_rows = frappe.get_all(
			'SD YRP Sewing Plan Order Detail',
			filters={"parent": ["in", list(entry_plan_names)], "fi_date": ["is", "not set"]},
			fields=["parent", "item_variant", "set_combination"],
			limit_page_length=0,
		)
		order_attributes = _variant_attributes({row.item_variant for row in order_rows})
		for row in order_rows:
			plan = plan_map.get(row.parent)
			lot = lots.get(plan.lot) if plan else None
			ipd = ipds.get(lot.production_detail) if lot else None
			if not plan or not ipd:
				continue
			bucket, _size = _bucket(row, ipd, order_attributes)
			key = (plan.lot, bucket["key"], bucket["part"])
			if key in seen:
				continue
			seen.add(key)
			pending_fi.append(
				{"lot": plan.lot, "colour": bucket["key"], "part": bucket["part"]}
			)

	headers = _input_types([row.input_type for row in entries])
	return {
		"headers": headers,
		"dpr_data": {} if pending_fi else dpr_data,
		"pending_fi": pending_fi,
	}


@frappe.whitelist()
def get_monthly_summary_data(
	supplier, start_date, end_date, input_type=None, show_grn=0
):
	start_date = getdate(start_date)
	end_date = getdate(end_date)
	if start_date > end_date:
		frappe.throw(_("Start Date cannot be after End Date."))
	plans = _plans(supplier)
	plan_map = {row.name: row for row in plans}
	lots, ipds = _metadata(plans)
	rows = []
	if cint(show_grn):
		frappe.has_permission('YRP Goods Received Note', "read", throw=True)
		work_orders = [row.work_order for row in plans if row.work_order]
		if work_orders:
			grns = frappe.get_list(
				'YRP Goods Received Note',
				filters={
					"supplier": supplier,
					"against": 'YRP Work Order',
					"against_id": ["in", work_orders],
					"posting_date": ["between", [start_date, end_date]],
					"docstatus": 1,
				},
				fields=["name", "posting_date", "lot"],
				limit_page_length=0,
			)
			grn_map = {row.name: row for row in grns}
			for row in frappe.get_all(
				'YRP Goods Received Note Item',
				filters={"parent": ["in", list(grn_map)]},
				fields=["parent", "item_variant", "quantity"],
				limit_page_length=0,
			):
				grn = grn_map[row.parent]
				lot = lots.get(grn.lot)
				ipd = ipds.get(lot.production_detail) if lot else None
				part = (
					get_variant_attr_details(row.item_variant).get(ipd.set_item_attribute)
					if ipd and ipd.is_set_item
					else ""
				)
				rows.append((grn.posting_date, lot.item if lot else "", part, row.quantity))
	else:
		if not input_type:
			frappe.throw(_("Input Type is required."))
		entries = [
			row
			for row in _entries(plans, input_type=input_type)
			if start_date <= getdate(row.entry_date) <= end_date
		]
		entry_map = {row.name: row for row in entries}
		for row in _details(entries):
			entry = entry_map[row.parent]
			plan = plan_map[entry.sewing_plan]
			lot = lots.get(plan.lot)
			ipd = ipds.get(lot.production_detail) if lot else None
			part = (
				get_variant_attr_details(row.item_variant).get(ipd.set_item_attribute)
				if ipd and ipd.is_set_item
				else ""
			)
			rows.append((entry.entry_date, plan.item, part, row.quantity))
	return _monthly_pivot(rows)


def _monthly_pivot(rows):
	totals = defaultdict(float)
	styles = set()
	for entry_date, style, part, quantity in rows:
		key = f"{style} ({part})" if part else style
		if not key:
			continue
		styles.add(key)
		totals[(str(entry_date), key)] += flt(quantity)
	styles = sorted(styles)
	dates = sorted({key[0] for key in totals})
	output = []
	grand_total = {style: 0 for style in styles}
	grand_total["total"] = 0
	for entry_date in dates:
		row = {"date": entry_date, "total": 0}
		for style in styles:
			row[style] = totals[(entry_date, style)]
			row["total"] += row[style]
			grand_total[style] += row[style]
		grand_total["total"] += row["total"]
		output.append(row)
	return {"styles": styles, "rows": output, "grand_total": grand_total}


@frappe.whitelist()
def get_monthly_summary_print_data(supplier=None):
	supplier = supplier or frappe.form_dict.get("supplier") or frappe.form_dict.get("name")
	start_date = frappe.form_dict.get("start_date") or today()
	end_date = frappe.form_dict.get("end_date") or start_date
	show_grn = cint(frappe.form_dict.get("show_grn"))
	input_type = frappe.form_dict.get("input_type")
	if not show_grn and not input_type:
		input_type = next(iter(_input_types()), None)
	data = get_monthly_summary_data(
		supplier,
		start_date,
		end_date,
		input_type,
		show_grn,
	)
	for row in data["rows"]:
		for key in [*data["styles"], "total"]:
			row[key] = _display_quantity(row.get(key))
	for key in [*data["styles"], "total"]:
		data["grand_total"][key] = _display_quantity(data["grand_total"].get(key))
	data.update(
		{
			"supplier": supplier,
			"start_date": start_date,
			"end_date": end_date,
			"input_type": input_type,
			"show_grn": show_grn,
		}
	)
	return data


def _display_quantity(value):
	return "-" if not flt(value) else frappe.format_value(value, {"fieldtype": "Float"})


@frappe.whitelist()
def get_item_summary_options(supplier):
	plans = _plans(supplier)
	return {
		"lots": sorted({row.lot for row in plans if row.lot}),
		"items": sorted({row.item for row in plans if row.item}),
	}


@frappe.whitelist()
def get_item_summary_data(supplier, lots=None, items=None):
	lots = _json_list(lots)
	items = _json_list(items)
	if not lots and not items:
		frappe.throw(_("Select at least one Lot or Item."))
	plans = _plans(supplier, lots=lots, items=items)
	entries = _entries(plans)
	detail_rows = _details(entries)
	plan_map = {row.name: row for row in plans}
	entry_map = {row.name: row for row in entries}
	lot_map, ipds = _metadata(plans)
	attributes = _variant_attributes({row.item_variant for row in detail_rows})
	groups = {}
	for row in detail_rows:
		entry = entry_map[row.parent]
		plan = plan_map[entry.sewing_plan]
		lot = lot_map.get(plan.lot)
		ipd = ipds.get(lot.production_detail) if lot else None
		if not ipd:
			continue
		bucket, size = _bucket(row, ipd, attributes)
		group = groups.setdefault(
			(plan.item, plan.lot),
			{"sizes": set(), "is_set_item": ipd.is_set_item, "ipd": ipd.name, "rows": {}},
		)
		key = (
			str(entry.entry_date),
			entry.input_type,
			entry.work_station or "",
			bucket["key"],
			bucket["part"],
		)
		group["sizes"].add(size)
		group["rows"].setdefault(key, defaultdict(float))[size] += flt(row.quantity)

	output = []
	for (item, lot), group in sorted(groups.items()):
		primary = get_ipd_primary_values(group["ipd"])
		headers = [value for value in primary if value in group["sizes"]]
		headers.extend(sorted(group["sizes"] - set(headers)))
		rows = []
		for key, values in sorted(group["rows"].items()):
			entry_date, input_type, work_station, colour, part = key
			rows.append(
				{
					"date": entry_date,
					"input_type": input_type,
					"work_station": work_station,
					"colour": colour,
					"part": part,
					"values": dict(values),
					"total": sum(values.values()),
				}
			)
		output.append(
			{
				"item": item,
				"lot": lot,
				"headers": headers,
				"has_part": group["is_set_item"],
				"rows": rows,
			}
		)
	return {"groups": output}


@frappe.whitelist()
def get_fi_updates_data(supplier):
	plans = _plans(supplier)
	plan_map = {row.name: row for row in plans}
	lots, ipds = _metadata(plans)
	rows = frappe.get_all(
		'SD YRP Sewing Plan Order Detail',
		filters={"parent": ["in", list(plan_map)], "fi_date": ["is", "not set"]},
		fields=["parent", "item_variant", "set_combination"],
		limit_page_length=0,
	) if plan_map else []
	attributes = _variant_attributes({row.item_variant for row in rows})
	seen = set()
	data = []
	for row in rows:
		plan = plan_map[row.parent]
		lot = lots.get(plan.lot)
		ipd = ipds.get(lot.production_detail) if lot else None
		if not ipd:
			continue
		bucket, _size = _bucket(row, ipd, attributes)
		key = (plan.lot, bucket["key"], bucket["part"])
		if key in seen:
			continue
		seen.add(key)
		data.append(
			{
				"colour": bucket["key"],
				"part": bucket["part"],
				"sewing_plan": plan.name,
				"lot": plan.lot,
				"item": plan.item,
				"is_set_item": ipd.is_set_item,
				"set_attr": ipd.set_item_attribute,
			}
		)
	return {"data": data}


@frappe.whitelist()
def update_fi_dates(data):
	data = _json_list(data)
	by_plan = defaultdict(list)
	for row in data:
		if isinstance(row, dict) and row.get("sewing_plan"):
			by_plan[row["sewing_plan"]].append(row)
	for plan_name, updates in by_plan.items():
		plan = frappe.get_doc('SD YRP Sewing Plan', plan_name)
		plan.check_permission("write")
		lot = frappe.get_doc('SD YRP Lot', plan.lot)
		ipd = frappe.get_doc('YRP Item Production Detail', lot.production_detail)
		attributes = _variant_attributes(
			{row.item_variant for row in plan.sewing_plan_order_details}
		)
		for update in updates:
			if update.get("lot") != plan.lot:
				frappe.throw(_("Sewing Plan and Lot do not match."))
			for row in plan.sewing_plan_order_details:
				bucket, _size = _bucket(row, ipd, attributes)
				if bucket["key"] == update.get("colour") and bucket["part"] == update.get("part"):
					row.fi_date = getdate(update["date"]) if update.get("date") else None
		plan.save()
	return _("Success")


@frappe.whitelist()
def get_the_lot(supplier):
	return {"lots": [{"lot": row.lot} for row in _plans(supplier) if row.lot]}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_supplier_lots(doctype, txt, searchfield, start, page_len, filters):
	filters = update_if_string_instance(filters) or {}
	supplier = filters.get("supplier") if isinstance(filters, dict) else None
	if not supplier:
		return []
	needle = cstr(txt).lower()
	rows = []
	for row in _plans(supplier):
		if needle and needle not in cstr(row.lot).lower() and needle not in cstr(row.item).lower():
			continue
		value = [row.lot, row.item]
		if value not in rows:
			rows.append(value)
	rows.sort(key=lambda value: (value[0] or "", value[1] or ""))
	return rows[cint(start) : cint(start) + cint(page_len or 20)]


@frappe.whitelist()
def get_consumption_mapping_data(lot, supplier=None):
	frappe.has_permission('YRP Item Production Detail', "read", throw=True)
	lot_doc = frappe.get_doc('SD YRP Lot', lot)
	lot_doc.check_permission("read")
	if not lot_doc.production_detail:
		return {"ipd": "", "sections": [], "cloth_acc_data": []}
	ipd = frappe.get_doc('YRP Item Production Detail', lot_doc.production_detail)
	process = ipd.get("stiching_process")
	if not process:
		return {"ipd": ipd.name, "sections": [], "cloth_acc_data": []}

	saved_qty = {}
	saved_cloth = {}
	if supplier:
		for plan_row in _plans(supplier, lots=[lot]):
			plan = frappe.get_doc('SD YRP Sewing Plan', plan_row.name)
			for row in plan.consumption_details:
				saved_qty[(row.item_name, cint(row.index))] = flt(row.consumption_qty)
			for row in plan.cloth_accessory_consumption:
				saved_cloth[cint(row.index)] = flt(row.consumption_weight)

	bom_rows = [
		row
		for row in ipd.item_bom
		if row.process_name == process and row.uom not in ("Nos", "Pieces")
	]
	mappings = [row.attribute_mapping for row in bom_rows if row.attribute_mapping]
	values_by_mapping = defaultdict(list)
	attributes_by_mapping = defaultdict(list)
	if mappings:
		for row in frappe.get_all(
			'YRP Item BOM Attribute Mapping Value',
			filters={"parent": ["in", mappings]},
			fields=["parent", "index", "type", "idx", "attribute", "attribute_value", "quantity"],
			order_by="parent asc, index asc, idx asc",
			limit_page_length=0,
		):
			values_by_mapping[row.parent].append(row)
		for row in frappe.get_all(
			'YRP Item BOM Attribute Mapping Attribute',
			filters={"parent": ["in", mappings], "same_attribute": 0},
			fields=["parent", "attribute"],
			limit_page_length=0,
		):
			attributes_by_mapping[row.parent].append(row.attribute)

	sections = []
	for bom in bom_rows:
		mapping_rows = {}
		column_names = []
		for row in values_by_mapping.get(bom.attribute_mapping, []):
			mapping = mapping_rows.setdefault(
				cint(row.index), {"quantity": row.quantity, "values": {}}
			)
			key = f"{row.type}_{row.attribute}"
			mapping["values"][key] = row.attribute_value
			mapping["quantity"] = row.quantity
			if key not in column_names:
				column_names.append(key)
		rows = [
			{
				"index": index,
				"values": value["values"],
				"quantity": saved_qty.get((bom.item, index), 0),
				"item_bom_qty": flt(value["quantity"]),
			}
			for index, value in sorted(mapping_rows.items())
		]
		if not rows:
			column_names = ['YRP Item']
			rows = [
				{
					"index": 0,
					"values": {'YRP Item': bom.item},
					"quantity": saved_qty.get((bom.item, 0), 0),
					"item_bom_qty": flt(bom.qty_of_bom_item),
				}
			]
		sections.append(
			{
				"item": bom.item,
				"item_attributes": column_names,
				"rows": rows,
				"attribute_in_item": attributes_by_mapping.get(bom.attribute_mapping, []),
				"item_bom_uom": bom.uom,
			}
		)

	cloth_data = update_if_string_instance(ipd.get("cloth_accessory_json")) or {}
	if isinstance(cloth_data, list):
		cloth_data = cloth_data[0] if cloth_data else {}
	columns = []
	for index, row in enumerate(cloth_data.get("items") or [], start=1):
		row = dict(row)
		row["Consumption Weight"] = saved_cloth.get(index, row.get("Consumption Weight", 0))
		columns.append(row)
	cloth_acc_data = []
	if columns:
		attributes = cloth_data.get("attributes") or []
		cloth_acc_data.append(
			{
				"accessory_type": list(cloth_data.get("select_list") or []),
				"attributes": attributes,
				"columns": columns,
				"att_iv_check": [
					value for value in attributes if value not in ("Accessory", "Dia", "Weight")
				],
			}
		)
	return {"ipd": ipd.name, "sections": sections, "cloth_acc_data": cloth_acc_data}


@frappe.whitelist()
def get_sewing_consumption_print_data(ipd, lot=None):
	lot = lot or frappe.db.get_value('SD YRP Lot', {"production_detail": ipd}, "name")
	if not lot:
		return {"ipd": ipd, "lot": "", "supplier": "", "sections": [], "cloth_acc_data": []}
	supplier = frappe.db.get_value('SD YRP Sewing Plan', {"lot": lot}, "supplier")
	data = get_consumption_mapping_data(lot, supplier)
	data.update({"lot": lot, "supplier": supplier})
	return data


@frappe.whitelist()
def save_consumption_data(supplier, lot, sections, cloth_acc_data=None):
	sections = _json_list(sections)
	cloth_acc_data = _json_list(cloth_acc_data)
	plans = _plans(supplier, lots=[lot])
	if not plans:
		frappe.throw(_("No Sewing Plan found for this Sewing Unit and Lot."))
	for plan_row in plans:
		plan = frappe.get_doc('SD YRP Sewing Plan', plan_row.name)
		plan.check_permission("write")
		_set_consumption_details(plan, sections)
		_set_cloth_accessory_details(plan, cloth_acc_data)
		plan.save()
	return {"status": "success", "message": _("Consumption data saved successfully")}


def _set_consumption_details(plan, sections):
	plan.set("consumption_details", [])
	variant_attributes = [
		get_variant_attr_details(row.item_variant) or {}
		for row in plan.sewing_plan_order_details
	]
	for section in sections:
		attributes_in_item = set(section.get("attribute_in_item") or [])
		for row in section.get("rows") or []:
			values = row.get("values") or {}
			details = []
			required = {}
			for key in section.get("item_attributes") or []:
				value = values.get(key)
				if value in (None, ""):
					continue
				row_type = "item" if cstr(key).startswith("item_") else "bom"
				attribute = cstr(key).split("_", 1)[1] if "_" in cstr(key) else key
				if row_type == "item":
					if attribute not in attributes_in_item:
						continue
					required[attribute] = value
				details.append((row_type, attribute, value))
			if required and not any(
				all(attrs.get(name) == value for name, value in required.items())
				for attrs in variant_attributes
			):
				continue
			for row_type, attribute, value in details:
				plan.append(
					"consumption_details",
					{
						"item_name": section.get("item"),
						"index": cint(row.get("index")),
						"attribute": attribute,
						"attribute_value": value,
						"type": row_type,
						"item_bom_qty": flt(row.get("item_bom_qty")),
						"consumption_qty": flt(row.get("quantity")),
					},
				)


def _set_cloth_accessory_details(plan, groups):
	plan.set("cloth_accessory_consumption", [])
	variant_attributes = [
		get_variant_attr_details(row.item_variant) or {}
		for row in plan.sewing_plan_order_details
	]
	for group in groups:
		match_attributes = group.get("att_iv_check") or []
		if isinstance(match_attributes, dict):
			match_attributes = list(match_attributes)
		for index, row in enumerate(group.get("columns") or [], start=1):
			if not any(
				all(not row.get(name) or attrs.get(name) == row.get(name) for name in match_attributes)
				for attrs in variant_attributes
			):
				continue
			for attribute in group.get("attributes") or []:
				plan.append(
					"cloth_accessory_consumption",
					{
						"index": index,
						"attribute": attribute,
						"attribute_value": row.get(attribute),
						"weight_in_ipd": flt(row.get("Weight")),
						"consumption_weight": flt(
							row.get("Consumption Weight") or row.get("consumption_weight")
						),
					},
				)


def _json_list(value):
	if isinstance(value, str):
		value = frappe.parse_json(value or "[]")
	if value in (None, ""):
		return []
	if not isinstance(value, list):
		frappe.throw(_("Expected a JSON list."))
	return value
