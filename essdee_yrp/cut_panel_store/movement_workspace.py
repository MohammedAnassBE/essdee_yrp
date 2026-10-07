"""Global Cut Panel Movement services for the Cut Panel Store workspace."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate, nowtime
from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
	_get_warehouse_for_supplier,
)

from essdee_yrp.cut_panel_store.common import assert_expected_modified, parse_json_object
from essdee_yrp.cutting.web_workspace import (
	_accessory_key,
	_apply_authoritative_movement_selection,
	_collapsed_key,
	_exact_bundle_key,
	_movement_payload as _cutting_movement_payload,
	_validate_movement_data,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cut_panel_movement.sd_yrp_cut_panel_movement import (
	get_cut_bundle_unmoved_data,
	get_total,
)

MOVEMENT_DOCTYPE = "SD YRP Cut Panel Movement"


def _empty_movement_data() -> dict:
	return {
		"panels": [],
		"data": {},
		"accessory_data": [],
		"collapsed_details": [],
		"is_set_item": 0,
	}


def _movement_context(doc=None, source=None) -> frappe._dict:
	"""Resolve immutable movement identity from the current document or Lot."""

	source = parse_json_object(source, label=_("Source"))
	lot = doc.lot if doc else source.get("lot")
	supplier = doc.from_warehouse if doc else source.get("from_warehouse")
	context = frappe._dict(
		lot=lot,
		item=None,
		production_detail=None,
		source_supplier=supplier,
		source_warehouse=None,
		movement_from_cutting=cint(doc.movement_from_cutting) if doc else 0,
		cutting_plan=doc.cutting_plan if doc else None,
	)
	if lot:
		lot_doc = frappe.get_doc("SD YRP Lot", lot)
		lot_doc.check_permission("read")
		context.item = lot_doc.item
		context.production_detail = lot_doc.production_detail
	if supplier:
		if not frappe.db.exists("Supplier", supplier):
			frappe.throw(_("Supplier {0} does not exist.").format(supplier))
		context.source_warehouse = _get_warehouse_for_supplier(supplier)
	return context


def _require_generation_context(context) -> None:
	if not context.lot:
		frappe.throw(_("Select a Lot before generating bundles."))
	if not context.source_supplier:
		frappe.throw(_("Select a From Warehouse before generating bundles."))
	if not context.item:
		frappe.throw(_("Lot {0} has no Item.").format(context.lot))


def _selected_exact_rows(data) -> list[tuple]:
	selected = []
	panels = data.get("panels") or []
	for colour, detail in (data.get("data") or {}).items():
		group_panels = panels if isinstance(panels, list) else panels.get(detail.get("part"), [])
		for row in detail.get("data") or []:
			if cint(row.get("bundle_moved")) or any(cint(row.get(f"{panel}_moved")) for panel in group_panels):
				selected.append((_exact_bundle_key(colour, row), group_panels, row))
	return selected


def _assert_known_selection(available: dict, selected: dict) -> None:
	available_exact = {}
	available_panels = available.get("panels") or []
	for colour, detail in (available.get("data") or {}).items():
		group_panels = available_panels if isinstance(available_panels, list) else available_panels.get(detail.get("part"), [])
		for row in detail.get("data") or []:
			available_exact[_exact_bundle_key(colour, row)] = (set(group_panels), row)

	for key, selected_panels, row in _selected_exact_rows(selected):
		candidate = available_exact.get(key)
		if not candidate:
			frappe.throw(_("Stock changed while this movement was open. Generate bundles again."))
		known_panels, _available_row = candidate
		for fieldname, value in row.items():
			if fieldname.endswith("_moved") and fieldname != "bundle_moved" and cint(value):
				if fieldname.removesuffix("_moved") not in known_panels:
					frappe.throw(_("Stock changed while this movement was open. Generate bundles again."))
		if any(panel not in known_panels for panel in selected_panels):
			frappe.throw(_("Stock changed while this movement was open. Generate bundles again."))

	available_collapsed = {_collapsed_key(row) for row in available.get("collapsed_details") or []}
	for row in selected.get("collapsed_details") or []:
		if (cint(row.get("moved")) or flt(row.get("move_qty")) > 0) and _collapsed_key(row) not in available_collapsed:
			frappe.throw(_("Stock changed while this movement was open. Generate bundles again."))

	available_accessories = {_accessory_key(row) for row in available.get("accessory_data") or []}
	for row in selected.get("accessory_data") or []:
		if flt(row.get("moved_weight")) > 0 and _accessory_key(row) not in available_accessories:
			frappe.throw(_("Stock changed while this movement was open. Generate bundles again."))


def _available_movement(context, posting_date=None, posting_time=None) -> dict:
	_require_generation_context(context)
	return get_cut_bundle_unmoved_data(
		context.source_supplier,
		context.lot,
		posting_date or nowdate(),
		posting_time or nowtime(),
		context.movement_from_cutting,
		cutting_plan=context.cutting_plan if context.movement_from_cutting else None,
		get_collapsed=True,
	)


def _authoritative_selection(values, doc=None) -> dict:
	values = parse_json_object(values)
	context = _movement_context(doc=doc, source=values)
	selected = _validate_movement_data(values.get("movement_data"))
	available = _available_movement(
		context,
		values.get("posting_date") or (doc.posting_date if doc else None),
		values.get("posting_time") or (doc.posting_time if doc else None),
	)
	_assert_known_selection(available, selected)
	return _apply_authoritative_movement_selection(available, selected)


def _movement_payload(doc, *, include_data=False) -> dict:
	payload = _cutting_movement_payload(doc, include_data=include_data)
	payload.update(
		{
			"movement_from_cutting": cint(doc.movement_from_cutting),
			"cutting_plan": doc.cutting_plan,
			"edit_posting_date_and_time": cint(doc.edit_posting_date_and_time),
		}
	)
	return payload


def _editor_payload(context, doc=None) -> dict:
	if doc:
		movement_data = parse_json_object(doc.cut_panel_movement_json, label=_("Movement Details"))
	else:
		movement_data = _empty_movement_data()
	return {
		"context": context,
		"record": _movement_payload(doc, include_data=True) if doc else None,
		"defaults": {
			"lot": context.lot,
			"from_warehouse": context.source_supplier,
			"posting_date": doc.posting_date if doc else nowdate(),
			"posting_time": doc.posting_time if doc else nowtime(),
			"edit_posting_date_and_time": cint(doc.edit_posting_date_and_time) if doc else 0,
		},
		"movement_data": movement_data,
		"permissions": {
			"can_create": bool(frappe.has_permission(MOVEMENT_DOCTYPE, ptype="create")),
			"can_submit": bool(frappe.has_permission(MOVEMENT_DOCTYPE, ptype="submit")),
		},
	}


@frappe.whitelist()
def get_movement_editor(name: str | None = None, source=None) -> dict:
	if name:
		doc = frappe.get_doc(MOVEMENT_DOCTYPE, name)
		doc.check_permission("read")
		return _editor_payload(_movement_context(doc=doc), doc)
	frappe.has_permission(MOVEMENT_DOCTYPE, ptype="create", throw=True)
	return _editor_payload(_movement_context(source=source))


@frappe.whitelist()
def generate_movement_bundles(values) -> dict:
	frappe.has_permission(MOVEMENT_DOCTYPE, ptype="create", throw=True)
	values = parse_json_object(values)
	context = _movement_context(source=values)
	return _available_movement(context, values.get("posting_date"), values.get("posting_time"))


def _apply_identity(doc, context, *, is_new: bool) -> None:
	if not is_new:
		return
	doc.lot = context.lot
	doc.item = context.item
	doc.from_warehouse = context.source_supplier
	doc.movement_from_cutting = 0
	doc.cutting_plan = None


@frappe.whitelist()
def save_movement(values, name: str | None = None, submit=False, expected_modified=None) -> dict:
	values = parse_json_object(values)
	is_new = not name
	if is_new:
		frappe.has_permission(MOVEMENT_DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(MOVEMENT_DOCTYPE)
		context = _movement_context(source=values)
	else:
		doc = frappe.get_doc(MOVEMENT_DOCTYPE, name)
		doc.check_permission("write")
		assert_expected_modified(doc, expected_modified)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a Draft Cut Panel Movement can be edited."))
		context = _movement_context(doc=doc)

	_require_generation_context(context)
	_apply_identity(doc, context, is_new=is_new)
	doc.edit_posting_date_and_time = cint(values.get("edit_posting_date_and_time"))
	if is_new or doc.edit_posting_date_and_time:
		doc.posting_date = values.get("posting_date") or nowdate()
		doc.posting_time = values.get("posting_time") or nowtime()
	movement_data = _authoritative_selection(values, doc=doc)
	doc.movement_data = movement_data
	doc.cut_panel_movement_json = get_total(json.loads(json.dumps(movement_data)))
	doc.save()
	if cint(submit):
		doc.check_permission("submit")
		doc.submit()
	return _movement_payload(doc, include_data=True)


@frappe.whitelist()
def execute_movement_command(name, command, expected_modified=None) -> dict:
	doc = frappe.get_doc(MOVEMENT_DOCTYPE, name)
	assert_expected_modified(doc, expected_modified)
	if command == "submit":
		doc.check_permission("submit")
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a Draft Cut Panel Movement can be submitted."))
		values = {
			"posting_date": doc.posting_date,
			"posting_time": doc.posting_time,
			"movement_data": parse_json_object(doc.cut_panel_movement_json),
		}
		movement_data = _authoritative_selection(values, doc=doc)
		doc.movement_data = movement_data
		doc.cut_panel_movement_json = get_total(json.loads(json.dumps(movement_data)))
		doc.save()
		doc.submit()
	elif command == "cancel":
		doc.check_permission("cancel")
		if cint(doc.docstatus) != 1:
			frappe.throw(_("Only a Submitted Cut Panel Movement can be cancelled."))
		doc.cancel()
	else:
		frappe.throw(_("Unsupported Cut Panel Movement command."))
	return _movement_payload(doc, include_data=True)
