# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.fabric_ipd import (
	FABRIC_COLOUR_ATTRIBUTE,
	FABRIC_DIA_ATTRIBUTE,
	get_fabric_process_kind,
)


@frappe.whitelist()
def get_fabric_deliverable_context(work_order):
	"""Popup context: one row per Lot Fabric Detail whose IPD maps this WO's
	process to knitting/dyeing/compacting. Empty rows => not a fabric process."""
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("read")
	lot = _get_lot(wo)

	rows = []
	kind = None
	for fabric in lot.get("lot_fabric_details") or []:
		if not fabric.production_detail:
			continue
		ipd = frappe.get_cached_doc("Item Production Detail", fabric.production_detail)
		row_kind = get_fabric_process_kind(ipd, wo.process_name)
		if not row_kind:
			continue
		kind = row_kind
		rows.append({
			"fabric_row": fabric.name,
			"yarn_item": fabric.yarn_item,
			"cloth_item": fabric.cloth_item,
			"production_detail": fabric.production_detail,
			"kind": row_kind,
			"yarn_attributes": _item_attributes(fabric.yarn_item),
			"cloth_attributes": _item_attributes(fabric.cloth_item),
			# knitting renders BOTH yarn attribute selects (attr_i_*) and non-Dia
			# cloth attribute selects (cloth_attr_i_*) from this one dict, so it
			# must carry both items' options; other kinds only ever show cloth
			# attribute selects.
			"attribute_options": (
				{**_attribute_options(fabric.yarn_item), **_attribute_options(fabric.cloth_item)}
				if row_kind == "knitting"
				else _attribute_options(fabric.cloth_item)
			),
			"dia_options": [r.dia for r in ipd.get("knitting_dia_details") or []],
			"colour_from_options": [r.from_colour for r in ipd.get("dyeing_colour_details") or []],
			"dia_from_options": [r.from_dia for r in ipd.get("compacting_dia_details") or []],
		})

	return {"is_fabric_process": bool(rows), "kind": kind, "rows": rows}


@frappe.whitelist()
def calculate_fabric_deliverables(work_order, rows):
	"""User-entered deliverables (variant attrs + weight) -> receivables, 1:1 (v1).

	knitting:   deliver yarn variant,        receive cloth variant at target_dia
	dyeing:     deliver cloth (from colour), receive cloth with to_colour swapped
	compacting: deliver cloth (from dia),    receive cloth with to_dia swapped
	"""
	rows = frappe.parse_json(rows) if isinstance(rows, str) else rows
	wo = frappe.get_doc("Work Order", work_order)
	wo.check_permission("write")
	if wo.docstatus != 0:
		frappe.throw(_("Calculate can only update a draft Work Order."))

	lot = _get_lot(wo)
	fabric_rows = {f.name: f for f in lot.get("lot_fabric_details") or []}
	default_received_type = frappe.db.get_single_value("YRP Stock Settings", "default_received_type")
	if not default_received_type:
		frappe.throw(_("Set Default Received Type in YRP Stock Settings first."))

	from yrp.yrp.doctype.item.item import get_or_create_variant

	deliverables, receivables = [], []
	for entry in rows:
		weight = flt(entry.get("weight"))
		if weight <= 0:
			continue
		fabric = fabric_rows.get(entry.get("fabric_row"))
		if not fabric:
			frappe.throw(_("Unknown Lot fabric row {0}.").format(entry.get("fabric_row")))
		ipd = frappe.get_cached_doc("Item Production Detail", fabric.production_detail)
		kind = get_fabric_process_kind(ipd, wo.process_name)
		if not kind:
			frappe.throw(_("{0} is not a fabric process on IPD {1}.").format(wo.process_name, ipd.name))

		attrs = entry.get("attribute_values") or {}
		if kind in ("dyeing", "compacting"):
			_require_all_attributes(fabric.cloth_item, attrs, fabric.name)

		if kind == "knitting":
			target_dia = entry.get("target_dia")
			valid = [r.dia for r in ipd.get("knitting_dia_details") or []]
			if target_dia not in valid:
				frappe.throw(_("Dia {0} is not configured on IPD {1}.").format(target_dia, ipd.name))
			# create_variant requires EVERY template attribute -> the popup
			# collects the non-Dia cloth attributes (e.g. greige Colour) too.
			out_attrs = dict(entry.get("cloth_attribute_values") or {})
			out_attrs[FABRIC_DIA_ATTRIBUTE] = target_dia
			_require_all_attributes(fabric.cloth_item, out_attrs, fabric.name)
			_require_all_attributes(fabric.yarn_item, attrs, fabric.name)
			in_variant = get_or_create_variant(fabric.yarn_item, attrs)
			out_variant = get_or_create_variant(fabric.cloth_item, out_attrs)
			in_item, out_item = fabric.yarn_item, fabric.cloth_item
		elif kind == "dyeing":
			mapping = {r.from_colour: r.to_colour for r in ipd.get("dyeing_colour_details") or []}
			out_attrs = _swap(attrs, FABRIC_COLOUR_ATTRIBUTE, mapping, ipd)
			in_variant = get_or_create_variant(fabric.cloth_item, attrs)
			out_variant = get_or_create_variant(fabric.cloth_item, out_attrs)
			in_item = out_item = fabric.cloth_item
		else:  # compacting
			mapping = {r.from_dia: r.to_dia for r in ipd.get("compacting_dia_details") or []}
			out_attrs = _swap(attrs, FABRIC_DIA_ATTRIBUTE, mapping, ipd)
			in_variant = get_or_create_variant(fabric.cloth_item, attrs)
			out_variant = get_or_create_variant(fabric.cloth_item, out_attrs)
			in_item = out_item = fabric.cloth_item

		deliverables.append({
			"item_variant": in_variant,
			"qty": weight,
			"uom": frappe.db.get_value("Item", in_item, "default_unit_of_measure"),
			"pending_quantity": weight,
			"received_type": default_received_type,
			"is_calculated": 1,
		})
		# v1: receivable strictly 1:1 with the entered deliverable weight
		receivables.append({
			"item_variant": out_variant,
			"qty": weight,
			"uom": frappe.db.get_value("Item", out_item, "default_unit_of_measure"),
			"pending_quantity": weight,
		})

	if not deliverables:
		frappe.throw(_("Enter a weight greater than zero for at least one fabric row."))

	# Idempotent rewrite (MGK pattern): drop prior calculated deliverables,
	# replace receivables wholesale, clear the grouped-JSON so sync_vue_item_details
	# doesn't resurrect stale rows.
	kept = [d for d in wo.get("deliverables") or [] if not d.get("is_calculated")]
	wo.set("deliverables", kept)
	for d in deliverables:
		wo.append("deliverables", d)
	wo.set("receivables", [])
	for r in receivables:
		wo.append("receivables", r)
	wo.deliverable_details = ""
	wo.receivable_details = ""
	wo.save()

	return {"deliverables": len(deliverables), "receivables": len(receivables)}


def _get_lot(wo):
	if not wo.get("lot"):
		frappe.throw(_("Select a Lot on the Work Order first."))
	lot = frappe.get_doc("Lot", wo.lot)
	lot.check_permission("read")
	return lot


def _item_attributes(item):
	if not item:
		return []
	doc = frappe.get_cached_doc("Item", item)
	return [row.attribute for row in doc.get("attributes") or []]


def _attribute_options(item):
	"""{attribute: [attribute_value, ...]} for every attribute of `item`."""
	options = {}
	for attribute in _item_attributes(item):
		options[attribute] = frappe.get_all(
			"Item Attribute Value", filters={"attribute_name": attribute},
			pluck="name", order_by="attribute_value asc", limit_page_length=0,
		)
	return options


def _require_all_attributes(item, attrs, fabric_row):
	"""Friendly pre-check: create_variant throws a raw framework error on any
	missing template attribute — name the fabric row + attribute instead."""
	for attribute in _item_attributes(item):
		if not attrs.get(attribute):
			frappe.throw(_("Select a value for {0} on fabric row {1}.").format(attribute, fabric_row))


def _swap(attrs, attribute, mapping, ipd):
	current = attrs.get(attribute)
	if current not in mapping:
		frappe.throw(_("{0} value {1} has no mapping on IPD {2}.").format(attribute, current, ipd.name))
	out = dict(attrs)
	out[attribute] = mapping[current]
	return out
