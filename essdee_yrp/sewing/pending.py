"""Sewing Pending: one quantity type minus another, by colour and size, for open Sewing Work Orders."""

from __future__ import annotations

from collections import defaultdict

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import cstr, flt
from yrp.attribute_links import value as attribute_value
from yrp.yrp.doctype.yrp_item_production_detail.yrp_item_production_detail import get_ipd_primary_values

from essdee_yrp.sewing.entry import _variant_attributes
from essdee_yrp.sewing.read_models import _input_types, _json_list, _metadata, _natural_name_key, _plans
from essdee_yrp.sewing.reporting import _bucket_context

GRN_QUANTITY = "GRN Quantity"
QUANTITY_FIELDS = ("from_qty", "to_qty", "pending")


def get_pending_types() -> list[str]:
	return [*_input_types(), GRN_QUANTITY]


def validate_pending_types(types, from_type=None, to_type=None) -> tuple[str, str]:
	"""Default to MRP Settings' input and line output types; both must be known and different."""
	from_type, to_type = cstr(from_type).strip(), cstr(to_type).strip()
	if not from_type or not to_type:
		settings = frappe.get_cached_doc("SD YRP MRP Settings")
		from_type = from_type or settings.sewing_input_qty_type
		to_type = to_type or settings.sewing_line_output_type
	for value in (from_type, to_type):
		if value not in types:
			frappe.throw(_("{0} is not a Sewing Pending type.").format(frappe.bold(value or "-")))
	if from_type == to_type:
		frappe.throw(_("From Type and To Type must be different."))
	return from_type, to_type


@frappe.whitelist()
def get_sewing_pending_data(supplier, from_type=None, to_type=None, items=None, lots=None, work_station=None):
	"""Rows where From quantity exceeds To quantity, line-wise or, with GRN, work-order-wise."""
	types = get_pending_types()
	from_type, to_type = validate_pending_types(types, from_type, to_type)
	is_line_wise = GRN_QUANTITY not in (from_type, to_type)
	if work_station and not is_line_wise:
		frappe.throw(_("GRN Quantity is not recorded per Work Station. Clear the Work Station filter."))
	plans = get_open_plans(supplier, lots=_json_list(lots), items=_json_list(items))
	sources = [
		get_grn_rows(plans)
		if quantity_type == GRN_QUANTITY
		else get_entry_rows(plans, quantity_type, cstr(work_station).strip())
		for quantity_type in (from_type, to_type)
	]
	groups, totals = build_pending_groups(*get_pending_quantities(plans, sources, is_line_wise))
	return {
		"types": types,
		"from_type": from_type,
		"to_type": to_type,
		"is_line_wise": is_line_wise,
		"groups": groups,
		"totals": totals,
	}


def get_open_plans(supplier, *, lots=None, items=None):
	plans = _plans(supplier, lots=lots, items=items)
	work_orders = {row.work_order for row in plans if row.work_order}
	if not work_orders:
		return []
	open_work_orders = set(
		frappe.get_list(
			"YRP Work Order",
			filters={"name": ["in", list(work_orders)], "docstatus": 1, "open_status": "Open"},
			pluck="name",
			limit_page_length=0,
		)
	)
	return [row for row in plans if row.work_order in open_work_orders]


def get_entry_rows(plans, input_type, work_station):
	"""Entry quantities summed per plan, work station, variant and set combination."""
	if not plans:
		return []
	frappe.has_permission("SD YRP Sewing Plan Entry Detail", "read", throw=True)
	entry = frappe.qb.DocType("SD YRP Sewing Plan Entry Detail")
	detail = frappe.qb.DocType("SD YRP Sewing Plan Detail")
	query = (
		frappe.qb.from_(detail)
		.join(entry)
		.on(detail.parent == entry.name)
		.select(
			entry.sewing_plan,
			entry.work_station,
			detail.item_variant,
			detail.set_combination,
			Sum(detail.quantity).as_("quantity"),
		)
		.where(detail.parenttype == "SD YRP Sewing Plan Entry Detail")
		.where(entry.sewing_plan.isin([row.name for row in plans]))
		.where(entry.input_type == input_type)
		.groupby(entry.sewing_plan, entry.work_station, detail.item_variant, detail.set_combination)
	)
	if work_station:
		query = query.where(entry.work_station == work_station)
	return query.run(as_dict=True)


def get_grn_rows(plans):
	"""Submitted GRN receipts per Work Order variant, as maintained on its calculated items."""
	if not plans:
		return []
	frappe.has_permission("YRP Goods Received Note", "read", throw=True)
	calculated = frappe.qb.DocType("YRP Work Order Calculated Item")
	rows = (
		frappe.qb.from_(calculated)
		.select(
			calculated.parent,
			calculated.item_variant,
			calculated.set_combination,
			Sum(calculated.received_qty).as_("quantity"),
		)
		.where(calculated.parenttype == "YRP Work Order")
		.where(calculated.parent.isin(list({row.work_order for row in plans})))
		.groupby(calculated.parent, calculated.item_variant, calculated.set_combination)
		.run(as_dict=True)
	)
	plan_by_work_order = {row.work_order: row.name for row in plans}
	for row in rows:
		row.sewing_plan, row.work_station = plan_by_work_order[row.parent], ""
	return rows


def get_pending_quantities(plans, sources, is_line_wise):
	"""Key each source quantity by (work station, lot, item, work order) and (colour, part, size)."""
	lots, ipds = _metadata(plans) if plans else ({}, {})
	snapshot = frappe._dict(lots=lots, ipds=ipds)
	attributes = _variant_attributes(
		{row.item_variant for rows in sources for row in rows if row.item_variant}
	)
	plan_map = {row.name: row for row in plans}
	sizes = {}
	quantities = []
	for rows in sources:
		result = defaultdict(float)
		for row in rows:
			plan = plan_map[row.sewing_plan]
			ipd, bucket, size = _bucket_context(snapshot, plan, row, attributes)
			if ipd.name not in sizes:
				sizes[ipd.name] = get_ipd_primary_values(ipd.name)
			if is_line_wise:
				row_key = (cstr(row.work_station), plan.lot, plan.item, "", ipd.name)
			else:
				row_key = ("", plan.lot, plan.item, plan.work_order, ipd.name)
			cell = (cstr(bucket["key"]), cstr(attribute_value(bucket["part"])), size)
			result[(row_key, cell)] += flt(row.quantity)
		quantities.append(result)
	return (*quantities, sizes)


def build_pending_groups(from_quantities, to_quantities, sizes) -> tuple[list[dict], dict]:
	"""Keep colour-size cells whose difference is positive; rows sum their kept cells."""
	rows = {}
	for key in set(from_quantities) | set(to_quantities):
		from_qty, to_qty = flt(from_quantities.get(key)), flt(to_quantities.get(key))
		pending = flt(from_qty - to_qty)
		if pending <= 0:
			continue
		row_key, (colour, part, size) = key
		row = rows.setdefault(row_key, {"cells": {}, "from_qty": 0, "to_qty": 0})
		row["cells"][(colour, part, size)] = pending
		row["from_qty"] += from_qty
		row["to_qty"] += to_qty
	groups = {}
	for row_key in sorted(rows, key=lambda key: key[1:4]):
		work_station, lot, item, work_order, ipd = row_key
		row = {"work_station": work_station, "lot": lot, "item": item, "work_order": work_order}
		row.update(_colour_size_grid(rows[row_key], sizes.get(ipd) or []))
		groups.setdefault(work_station, []).append(row)
	output = [
		{"work_station": work_station, "rows": group_rows, "totals": _totals(group_rows)}
		for work_station, group_rows in sorted(groups.items(), key=lambda value: _natural_name_key(value[0]))
	]
	return output, _totals([row for group in output for row in group["rows"]])


def _colour_size_grid(row, size_order):
	observed = {size for _colour, _part, size in row["cells"]}
	headers = [size for size in size_order if size in observed]
	headers.extend(sorted(observed - set(headers)))
	colours = {}
	for (colour, part, size), pending in row["cells"].items():
		values = colours.setdefault((colour, part), {})
		values[size] = pending
	return {
		"from_qty": flt(row["from_qty"]),
		"to_qty": flt(row["to_qty"]),
		"pending": flt(sum(row["cells"].values())),
		"sizes": headers,
		"has_part": any(part for _colour, part in colours),
		"colours": [
			{"colour": colour or "-", "part": part, "values": values, "total": flt(sum(values.values()))}
			for (colour, part), values in sorted(colours.items())
		],
		"size_totals": {
			size: flt(
				sum(pending for (_c, _p, cell_size), pending in row["cells"].items() if cell_size == size)
			)
			for size in headers
		},
	}


def _totals(rows):
	return {field: flt(sum(row[field] for row in rows)) for field in QUANTITY_FIELDS}
