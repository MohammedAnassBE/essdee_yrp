"""Permission-aware Sewing Plan data entry with configured stage sequencing."""

from __future__ import annotations

from collections import defaultdict
import json

import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate, get_time, nowdate, nowtime

from yrp.utils import update_if_string_instance
from yrp.yrp.doctype.item_production_detail.item_production_detail import (
	get_ipd_primary_values,
)

from essdee_yrp.sewing.config import get_sewing_input_configuration


@frappe.whitelist()
def get_data_entry_data(supplier: str, lot: str | None = None) -> dict:
	"""Return the data-entry grid and configured predecessor for every stage."""

	supplier = cstr(supplier).strip()
	lot = cstr(lot).strip()
	if not supplier:
		frappe.throw(_("Sewing Unit is required."))
	input_configuration = get_sewing_input_configuration()

	filters = {"supplier": supplier}
	if lot:
		filters["lot"] = lot
	plans = frappe.get_list(
		"Sewing Plan",
		filters=filters,
		fields=["name", "lot", "item", "supplier", "work_order"],
		limit_page_length=0,
	)
	if not plans:
		return _empty_data_entry_response(input_configuration)

	plan_names = [row.name for row in plans]
	work_orders = {
		row.name: row
		for row in frappe.get_all(
			"Work Order",
			filters={"name": ["in", [row.work_order for row in plans]]},
			fields=["name", "production_detail", "open_status"],
		)
	}
	order_rows = frappe.get_all(
		"Sewing Plan Order Detail",
		filters={"parent": ["in", plan_names], "parenttype": "Sewing Plan"},
		fields=[
			"name",
			"parent",
			"item_variant",
			"set_combination",
			"quantity",
			"pre_final",
			"final_inspection",
		],
		limit_page_length=0,
	)
	entry_headers = frappe.get_list(
		"Sewing Plan Entry Detail",
		filters={"sewing_plan": ["in", plan_names]},
		fields=["name", "sewing_plan", "input_type"],
		limit_page_length=0,
	)
	entry_rows = []
	if entry_headers:
		entry_rows = frappe.get_all(
			"Sewing Plan Detail",
			filters={
				"parent": ["in", [row.name for row in entry_headers]],
				"parenttype": "Sewing Plan Entry Detail",
			},
			fields=["parent", "item_variant", "set_combination", "quantity"],
			limit_page_length=0,
		)

	variants = {
		row.item_variant for row in [*order_rows, *entry_rows] if row.item_variant
	}
	variant_attributes = _variant_attributes(variants)
	order_by_plan = _group_by(order_rows, "parent")
	entries_by_plan = _group_by(entry_headers, "sewing_plan")
	rows_by_entry = _group_by(entry_rows, "parent")

	ipd_names = {
		work_orders[row.work_order].production_detail
		for row in plans
		if work_orders.get(row.work_order)
		and work_orders[row.work_order].production_detail
	}
	ipds = {
		row.name: row
		for row in frappe.get_all(
			"Item Production Detail",
			filters={"name": ["in", list(ipd_names)]},
			fields=[
				"name",
				"is_set_item",
				"packing_attribute",
				"primary_item_attribute",
				"set_item_attribute",
			],
		)
	}

	data = {}
	for plan in plans:
		work_order = work_orders.get(plan.work_order)
		ipd = ipds.get(work_order.production_detail) if work_order else None
		if not ipd:
			continue
		plan_data = {
			"details": {
				"item": plan.item,
				"lot": plan.lot,
				"supplier": plan.supplier,
				"work_order": plan.work_order,
				"work_order_status": work_order.open_status,
				"primary_values": get_ipd_primary_values(ipd.name),
				"is_set_item": ipd.is_set_item,
				"pack_attr": ipd.packing_attribute,
				"primary_attr": ipd.primary_item_attribute,
				"set_attr": ipd.set_item_attribute,
			},
			"colours": {},
		}
		data.setdefault(plan.lot, {})[plan.name] = plan_data
		for row in order_by_plan.get(plan.name, []):
			bucket, size = _entry_bucket(row, ipd, variant_attributes)
			colour_data = plan_data["colours"].setdefault(
				bucket["key"],
				{
					"values": {},
					"part": bucket["part"],
					"colour": bucket["key"],
					"variant_colour": bucket["variant_colour"],
					"set_combination": bucket["set_combination"],
					"qty": 0,
					"inspection_total": {
						"pre_final": 0,
						"final_inspection": 0,
					},
				},
			)
			value = colour_data["values"].setdefault(
				size,
				{
					"order_detail": row.name,
					"item_variant": row.item_variant,
					"order_qty": 0,
					"data_entry": 0,
					"pre_final": 0,
					"final_inspection": 0,
				},
			)
			value["order_qty"] += flt(row.quantity)
			value["pre_final"] += flt(row.pre_final)
			value["final_inspection"] += flt(row.final_inspection)
			colour_data["qty"] += flt(row.quantity)
			colour_data["inspection_total"]["pre_final"] += flt(row.pre_final)
			colour_data["inspection_total"]["final_inspection"] += flt(
				row.final_inspection
			)

		for entry in entries_by_plan.get(plan.name, []):
			input_key = _input_key(entry.input_type)
			for row in rows_by_entry.get(entry.name, []):
				bucket, size = _entry_bucket(row, ipd, variant_attributes)
				colour_data = plan_data["colours"].get(bucket["key"])
				if not colour_data or size not in colour_data["values"]:
					continue
				value = colour_data["values"][size]
				value[input_key] = flt(value.get(input_key)) + flt(row.quantity)

	for plans_by_lot in data.values():
		for plan_data in plans_by_lot.values():
			for colour_data in plan_data["colours"].values():
				for value in colour_data["values"].values():
					for row in input_configuration:
						value[f"{row.input_key}_remaining"] = max(
							0,
							flt(value.get(row.difference_key))
							- flt(value.get(row.input_key)),
						)
	return {
		"data": data,
		"diff": {
			row.input_key: row.difference_key for row in input_configuration
		},
		"allowances": {
			row.input_key: row.allowance for row in input_configuration
		},
		"input_types": [row.input_type for row in input_configuration],
		"inspection_type": "pre_final",
		"default_received_type": frappe.db.get_single_value(
			"YRP Stock Settings", "default_received_type"
		),
	}


@frappe.whitelist()
def update_sewing_plan_data(payload) -> str:
	"""Update the persisted pre-final/final inspection matrix for one plan.

	The F15 workbench exposed this as its Update action. F16 resolves the selected
	rows against the saved plan rather than trusting browser-supplied variants.
	"""

	payload = _json_object(payload)
	plan_name = cstr(payload.get("plan")).strip()
	plan = frappe.get_doc("Sewing Plan", plan_name)
	plan.check_permission("write")
	if cstr(payload.get("lot")).strip() != plan.lot:
		frappe.throw(_("Sewing Plan and Lot do not match."))

	inspection_type = cstr(payload.get("inspection_type")).strip()
	if inspection_type not in {"pre_final", "final_inspection"}:
		frappe.throw(_("Select Pre Final or Final Inspection."))
	action = cstr(payload.get("action") or "update").strip()
	if action not in {"update", "revert"}:
		frappe.throw(_("Invalid Sewing inspection action."))

	lot = frappe.get_doc("Lot", plan.lot)
	if not lot.production_detail:
		frappe.throw(_("Lot has no production detail."))
	ipd = frappe.get_doc("Item Production Detail", lot.production_detail)
	variant_attributes = _variant_attributes(
		{row.item_variant for row in plan.sewing_plan_order_details if row.item_variant}
	)

	selected = {}
	for row in payload.get("rows") or []:
		combination = update_if_string_instance(row.get("set_combination")) or {}
		combination_key = tuple(sorted(combination.items()))
		for size, values in (row.get("qty") or {}).items():
			quantity = 0 if action == "revert" else flt((values or {}).get(inspection_type))
			if quantity < 0:
				frappe.throw(_("Inspection quantity cannot be negative."))
			key = (
				cstr(row.get("colour")).strip(),
				cstr(row.get("part")).strip(),
				combination_key,
				cstr(size).strip(),
			)
			selected[key] = quantity

	updated = 0
	for order_row in plan.sewing_plan_order_details:
		bucket, size = _entry_bucket(order_row, ipd, variant_attributes)
		key = (
			cstr(bucket.get("variant_colour")).strip(),
			cstr(bucket.get("part")).strip(),
			tuple(sorted((bucket.get("set_combination") or {}).items())),
			cstr(size).strip(),
		)
		if key not in selected:
			continue
		quantity = selected[key]
		if quantity > flt(order_row.quantity):
			frappe.throw(
				_("Inspection quantity cannot exceed ordered quantity for {0}.").format(
					frappe.bold(order_row.item_variant)
				)
			)
		order_row.set(inspection_type, quantity)
		updated += 1

	if not updated:
		frappe.throw(_("No matching Sewing Plan rows were selected."))
	plan.save()
	return "Success"


@frappe.whitelist()
def submit_data_entry_log(payload) -> str:
	payload = _json_object(payload)
	frappe.has_permission("Sewing Plan Entry Detail", "create", throw=True)

	plan_name = cstr(payload.get("plan")).strip()
	plan = frappe.get_doc("Sewing Plan", plan_name)
	plan.check_permission("read")
	input_type = _required_link(payload, "input_type", "Sewing Plan Input Type")
	configuration = {
		row.input_type: row for row in get_sewing_input_configuration()
	}
	if input_type not in configuration:
		frappe.throw(
			_("{0} is not configured in Sewing Plan Input Orders.").format(
				frappe.bold(input_type)
			)
		)
	received_type = cstr(
		payload.get("received_type") or payload.get("grn_item_type")
	).strip()
	if not received_type or not frappe.db.exists("Received Type", received_type):
		frappe.throw(_("Select a valid Received Type."))
	work_station = _required_link(payload, "work_station", "Work Station")
	entry_date = getdate(payload.get("date") or nowdate())
	entry_time = get_time(payload.get("time") or nowtime())

	quantities = _json_object(payload.get("quantities"))
	rows = _trusted_entry_rows(plan, quantities)
	if not rows:
		frappe.throw(_("Enter a quantity for at least one Sewing Plan item."))
	frappe.db.sql(
		"select name from `tabSewing Plan` where name = %s for update",
		plan.name,
	)
	_validate_input_sequence(plan, configuration[input_type], rows)

	entry = frappe.new_doc("Sewing Plan Entry Detail")
	entry.sewing_plan = plan.name
	entry.input_type = input_type
	entry.received_type = received_type
	entry.work_station = work_station
	entry.entry_date = entry_date
	entry.entry_time = entry_time
	entry.posting_date = nowdate()
	entry.posting_time = nowtime()
	entry.set(
		"sewing_plan_details",
		[
			{key: value for key, value in row.items() if key != "_order_detail"}
			for row in rows
		],
	)
	entry.insert()
	return entry.name


@frappe.whitelist()
def cancel_sewing_plan_entry(doc_id: str) -> None:
	entry = frappe.get_doc("Sewing Plan Entry Detail", doc_id)
	entry.check_permission("delete")
	entry.delete()


def _trusted_entry_rows(plan, quantities) -> list[dict]:
	order_rows = {row.name: row for row in plan.sewing_plan_order_details}
	selected = defaultdict(float)
	for colour in (quantities.get("colours") or {}).values():
		for value in (colour.get("values") or {}).values():
			quantity = flt(value.get("data_entry"))
			if quantity < 0:
				frappe.throw(_("Sewing quantity cannot be negative."))
			if not quantity:
				continue
			order_detail = cstr(value.get("order_detail")).strip()
			if order_detail not in order_rows:
				frappe.throw(_("A selected Sewing item does not belong to this plan."))
			selected[order_detail] += quantity

	rows = []
	for order_detail, quantity in selected.items():
		source = order_rows[order_detail]
		rows.append(
			{
				"_order_detail": order_detail,
				"item_variant": source.item_variant,
				"set_combination": source.set_combination,
				"quantity": quantity,
			}
		)
	return rows


def _validate_input_sequence(plan, configuration, rows) -> None:
	"""Reject quantities that exceed the saved predecessor-stage balance."""

	# This is a locking/current read, not a repeatable-read snapshot. Together
	# with the parent Sewing Plan lock it serializes concurrent stage entries and
	# ensures the second request sees the first request's newly committed rows.
	detail_rows = frappe.db.sql(
		"""
			select
				entry.input_type,
				detail.item_variant,
				detail.set_combination,
				detail.quantity
			from `tabSewing Plan Entry Detail` entry
			join `tabSewing Plan Detail` detail on detail.parent = entry.name
			where entry.sewing_plan = %s
			  and detail.parenttype = 'Sewing Plan Entry Detail'
			for update
		""",
		plan.name,
		as_dict=True,
	)

	totals = defaultdict(float)
	for row in detail_rows:
		totals[
			(
				row.input_type,
				row.item_variant,
				_combination_key(row.set_combination),
			)
		] += flt(row.quantity)

	order_rows = {row.name: row for row in plan.sewing_plan_order_details}
	order_totals = defaultdict(float)
	for source in order_rows.values():
		identity = (source.item_variant, _combination_key(source.set_combination))
		order_totals[identity] += flt(source.quantity)
	requested = defaultdict(float)
	for row in rows:
		source = order_rows[row["_order_detail"]]
		identity = (source.item_variant, _combination_key(source.set_combination))
		requested[identity] += flt(row["quantity"])

	for identity, requested_quantity in requested.items():
		if configuration.difference_from == "Order Qty":
			predecessor_quantity = order_totals[identity]
		else:
			predecessor_quantity = totals[
				(configuration.difference_from, *identity)
			]
		already_entered = totals[(configuration.input_type, *identity)]
		allowed_total = predecessor_quantity * (1 + flt(configuration.allowance) / 100)
		remaining = max(0, allowed_total - already_entered)
		if requested_quantity <= remaining + 1e-9:
			continue
		frappe.throw(
			_(
				"Cannot record {0} for {1}. Only {2} remains from {3} "
				"after the configured {4}% allowance."
			).format(
				frappe.bold(configuration.input_type),
				frappe.bold(identity[0]),
				frappe.bold(frappe.format_value(remaining, {"fieldtype": "Float"})),
				frappe.bold(configuration.difference_from),
				frappe.format_value(configuration.allowance, {"fieldtype": "Percent"}),
			),
			title=_("Sewing Input Sequence Blocked"),
		)


def _combination_key(value) -> str:
	value = update_if_string_instance(value) or {}
	return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _entry_bucket(row, ipd, variant_attributes) -> tuple[dict, str]:
	attributes = variant_attributes.get(row.item_variant, {})
	combination = update_if_string_instance(row.set_combination) or {}
	major_colour = combination.get("major_colour", "")
	colour = major_colour
	part = None
	variant_colour = colour
	if ipd.is_set_item:
		variant_colour = attributes.get(ipd.packing_attribute, "")
		part = attributes.get(ipd.set_item_attribute, "")
		colour = variant_colour
		if combination.get("major_part") != part:
			colour = f"{variant_colour} ({major_colour})"
	return (
		{
			"key": colour,
			"part": part,
			"variant_colour": variant_colour,
			"set_combination": combination,
		},
		attributes.get(ipd.primary_item_attribute, ""),
	)


def _variant_attributes(variants) -> dict[str, dict]:
	if not variants:
		return {}
	result = defaultdict(dict)
	for row in frappe.get_all(
		"Item Variant Attribute",
		filters={"parent": ["in", list(variants)]},
		fields=["parent", "attribute", "attribute_value"],
		limit_page_length=0,
	):
		result[row.parent][row.attribute] = row.attribute_value
	return dict(result)


def _group_by(rows, fieldname):
	result = defaultdict(list)
	for row in rows:
		result[row.get(fieldname)].append(row)
	return result


def _required_link(payload, fieldname, doctype) -> str:
	value = cstr(payload.get(fieldname)).strip()
	if not value or not frappe.db.exists(doctype, value):
		frappe.throw(_("Select a valid {0}.").format(frappe.bold(doctype)))
	return value


def _input_key(value) -> str:
	return cstr(value).strip().lower().replace(" ", "_")


def _json_object(value) -> dict:
	if isinstance(value, str):
		value = frappe.parse_json(value or "{}")
	if not isinstance(value, dict):
		frappe.throw(_("Invalid Sewing Plan data."))
	return value


def _empty_data_entry_response(input_configuration=None) -> dict:
	input_configuration = input_configuration or get_sewing_input_configuration()
	return {
		"data": {},
		"diff": {
			row.input_key: row.difference_key for row in input_configuration
		},
		"allowances": {
			row.input_key: row.allowance for row in input_configuration
		},
		"input_types": [row.input_type for row in input_configuration],
		"inspection_type": "pre_final",
		"default_received_type": frappe.db.get_single_value(
			"YRP Stock Settings", "default_received_type"
		),
	}
