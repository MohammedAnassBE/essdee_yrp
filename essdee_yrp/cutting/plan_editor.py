"""Thin, permission-checked editor service for Cutting Plans in ``/web``."""

from __future__ import annotations


from copy import deepcopy

from yrp.attribute_read_context import attribute_read_scope
import frappe
from frappe import _
from frappe.model import get_permitted_fields
from frappe.utils import cint, flt, sbool

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
	fetch_order_item_details,
	get_items,
)


DOCTYPE = "SD YRP Cutting Plan"
LOT_DOCTYPE = "SD YRP Lot"
EDITABLE_FIELDS = {
	"is_manual_entry",
	"lot",
	"maximum_no_of_plys",
	"maximum_allow_percent",
	"cutting_location",
	"work_order",
	"item_details",
}
ROW_IDENTITY_FIELDS = ("name", "attributes", "item_keys", "primary_attribute")
STATUS_ACTIONS = {"submit", "cancel", "amend"}


def _parse_json(value, fallback):
	if value in (None, ""):
		return deepcopy(fallback)
	if isinstance(value, (dict, list)):
		return deepcopy(value)
	return frappe.parse_json(value)


def _doc_value(doc, fieldname, default=None):
	value = getattr(doc, fieldname, None)
	if value is not None:
		return value
	if hasattr(doc, "get"):
		return doc.get(fieldname, default)
	return default


def _row_key(group_index: int, row_index: int) -> str:
	return f"g{group_index}:r{row_index}"


def _with_row_keys(groups) -> list[dict]:
	keyed = _parse_json(groups, [])
	for group_index, group in enumerate(keyed):
		for row_index, row in enumerate(group.get("items") or []):
			row["_row_key"] = _row_key(group_index, row_index)
	return keyed


def _quantity(value, *, row_key: str, size: str) -> float:
	if isinstance(value, dict):
		value = value.get("qty")
	try:
		quantity = flt(value)
	except (TypeError, ValueError):
		frappe.throw(
			_("Enter a valid quantity for row {0}, size {1}.").format(row_key, size)
		)
	if quantity < 0:
		frappe.throw(
			_("Quantity cannot be negative for row {0}, size {1}.").format(row_key, size)
		)
	return quantity


def _merge_authoritative_matrix(authoritative_groups, incoming_groups) -> list[dict]:
	"""Copy only quantity cells from the browser into authoritative Lot rows."""

	authoritative = _with_row_keys(authoritative_groups)
	incoming = _parse_json(incoming_groups, [])
	expected = {
		row["_row_key"]: row
		for group in authoritative
		for row in (group.get("items") or [])
	}
	received = {}
	for group in incoming:
		for row in group.get("items") or []:
			key = row.get("_row_key")
			if not key or key not in expected:
				frappe.throw(_("The Cutting Plan contains an unknown item row."))
			if key in received:
				frappe.throw(_("The Cutting Plan contains a duplicate item row: {0}.").format(key))
			for fieldname in ROW_IDENTITY_FIELDS:
				if fieldname in row and row.get(fieldname) != expected[key].get(fieldname):
					frappe.throw(_("Item identity changed for row {0}. Reload the Lot and try again.").format(key))
			received[key] = row

	missing = set(expected) - set(received)
	if missing:
		frappe.throw(_("The Cutting Plan is missing item rows. Reload the Lot and try again."))

	for group in authoritative:
		primary_values = list(group.get("primary_attribute_values") or [])
		size_totals = {size: 0.0 for size in primary_values}
		group_total = 0.0
		for row in group.get("items") or []:
			key = row["_row_key"]
			incoming_values = received[key].get("values") or {}
			expected_sizes = set((row.get("values") or {}).keys())
			if set(incoming_values) != expected_sizes:
				frappe.throw(_("Sizes changed for row {0}. Reload the Lot and try again.").format(key))
			row_total = 0.0
			for size in row.get("values") or {}:
				quantity = _quantity(incoming_values[size], row_key=key, size=size)
				row["values"][size] = {"qty": quantity}
				size_totals[size] = size_totals.get(size, 0.0) + quantity
				row_total += quantity
			row["total_qty"] = row_total
			group_total += row_total
		group["size_wise_total"] = size_totals
		group["total_sum"] = group_total
	return authoritative


def _normalize_values(values) -> dict:
	values = _parse_json(values, {})
	if not isinstance(values, dict):
		frappe.throw(_("Cutting Plan values must be an object."))
	unknown = set(values) - EDITABLE_FIELDS
	if unknown:
		frappe.throw(
			_("These Cutting Plan fields cannot be changed here: {0}.").format(
				", ".join(sorted(unknown))
			)
		)
	return values


def _assert_field_permissions(values) -> None:
	"""Enforce DocField permlevels for direct RPC callers as well as the UI."""

	try:
		permitted = set(get_permitted_fields(DOCTYPE, permission_type="write"))
	except TypeError:
		permitted = set(get_permitted_fields(DOCTYPE, "write"))
	denied = (set(values) & EDITABLE_FIELDS) - permitted - {"item_details"}
	if denied:
		frappe.throw(
			_("You do not have permission to change these Cutting Plan fields: {0}.").format(
				", ".join(sorted(denied))
			),
			frappe.PermissionError,
		)


def _allow_on_submit_fields(doc, write_fields=None) -> list[str]:
	"""Return editable web fields that are genuinely writable after submit."""

	if cint(_doc_value(doc, "docstatus", 0)) != 1:
		return []
	if write_fields is None:
		try:
			write_fields = set(get_permitted_fields(DOCTYPE, permission_type="write"))
		except TypeError:
			write_fields = set(get_permitted_fields(DOCTYPE, "write"))
	meta = getattr(doc, "meta", None) or frappe.get_meta(DOCTYPE)
	allowed = []
	for fieldname in sorted(EDITABLE_FIELDS - {"item_details"}):
		field = meta.get_field(fieldname)
		if (
			field is None
			or fieldname not in write_fields
			or not bool(field.get("allow_on_submit"))
			or bool(field.get("hidden"))
			or bool(field.get("read_only"))
		):
			continue
		allowed.append(fieldname)
	return allowed


def _get_lot(lot: str):
	if not lot:
		frappe.throw(_("Lot is required."))
	lot_doc = frappe.get_doc(LOT_DOCTYPE, lot)
	check_permission = getattr(lot_doc, "check_permission", None)
	if callable(check_permission):
		check_permission("read")
	else:
		frappe.has_permission(LOT_DOCTYPE, ptype="read", doc=lot_doc, throw=True)
	return lot_doc


def _assert_not_stale(doc, expected_modified=None) -> None:
	if expected_modified and str(_doc_value(doc, "modified")) != str(expected_modified):
		frappe.throw(
			_("{0} changed after you opened it. Refresh and try again.").format(doc.name),
			frappe.TimestampMismatchError,
		)


def _permission_flags(doc=None) -> dict[str, bool]:
	docstatus = cint(_doc_value(doc, "docstatus", 0)) if doc is not None else None

	def allowed(ptype: str, *, record_sensitive: bool = True) -> bool:
		kwargs = {"ptype": ptype}
		if doc is not None and record_sensitive:
			kwargs["doc"] = doc
		return bool(frappe.has_permission(DOCTYPE, **kwargs))

	raw_write = allowed("write")
	permissions = {
		"can_read": allowed("read"),
		"can_create": allowed("create", record_sensitive=False),
		"can_write": raw_write,
		"can_update_after_submit": False,
		"can_submit": allowed("submit"),
		"can_cancel": allowed("cancel"),
		"can_amend": allowed("amend"),
	}
	if doc is not None:
		permissions["can_update_after_submit"] = bool(
			docstatus == 1 and raw_write and _allow_on_submit_fields(doc)
		)
		permissions["can_write"] = bool(docstatus == 0 and permissions["can_write"])
		permissions["can_submit"] = bool(docstatus == 0 and permissions["can_submit"])
		permissions["can_cancel"] = bool(docstatus == 1 and permissions["can_cancel"])
		permissions["can_amend"] = bool(docstatus == 2 and permissions["can_amend"])
	else:
		permissions["can_write"] = False
		permissions["can_update_after_submit"] = False
		permissions["can_cancel"] = False
		permissions["can_amend"] = False
	return permissions


def _record_payload(doc, include_work_order=False) -> dict:
	payload = {
		"name": _doc_value(doc, "name"),
		"docstatus": cint(_doc_value(doc, "docstatus", 0)),
		"modified": _doc_value(doc, "modified"),
		"is_manual_entry": cint(_doc_value(doc, "is_manual_entry", 0)),
		"lot": _doc_value(doc, "lot"),
		"item": _doc_value(doc, "item"),
		"production_detail": _doc_value(doc, "production_detail"),
		"maximum_no_of_plys": _doc_value(doc, "maximum_no_of_plys"),
		"maximum_allow_percent": _doc_value(doc, "maximum_allow_percent"),
		"cutting_location": _doc_value(doc, "cutting_location"),
		"status": _doc_value(doc, "cp_status") or "Draft",
	}
	if include_work_order:
		payload["work_order"] = _doc_value(doc, "work_order")
	return payload


def _saved_matrix(doc) -> list[dict]:
	items = _doc_value(doc, "items", []) or []
	production_detail = _doc_value(doc, "production_detail")
	if not items or not production_detail:
		return []
	return fetch_order_item_details(items, production_detail) or []


def _serialize_editor(doc, groups) -> dict:
	try:
		write_fields = set(get_permitted_fields(DOCTYPE, permission_type="write"))
		read_fields = set(get_permitted_fields(DOCTYPE, permission_type="read"))
	except TypeError:
		write_fields = set(get_permitted_fields(DOCTYPE, "write"))
		read_fields = set(get_permitted_fields(DOCTYPE, "read"))
	show_work_order = "work_order" in read_fields
	allow_on_submit_fields = _allow_on_submit_fields(doc, write_fields)
	return {
		"record": _record_payload(doc, include_work_order=show_work_order),
		"matrix": {"groups": _with_row_keys(groups)},
		"permissions": _permission_flags(doc if _doc_value(doc, "name") else None),
		"fields": {
			"show_work_order": show_work_order,
			"can_edit_work_order": "work_order" in write_fields,
			"allow_on_submit_fields": allow_on_submit_fields,
		},
		"options": {
			"cutting_locations": ["Machine Cutting", "Manual Cutting"],
		},
	}


@frappe.whitelist()
def load_lot_items(lot: str) -> dict:
	lot_doc = _get_lot(lot)
	return {
		"lot": lot_doc.name,
		"item": _doc_value(lot_doc, "item"),
		"production_detail": _doc_value(lot_doc, "production_detail"),
		"groups": _with_row_keys(get_items(lot) or []),
	}


@frappe.whitelist()
def get_editor(cutting_plan: str | None = None, lot: str | None = None) -> dict:
	with attribute_read_scope():
		return _build_editor(cutting_plan, lot)


def _build_editor(cutting_plan: str | None = None, lot: str | None = None) -> dict:
	if cutting_plan:
		doc = frappe.get_doc(DOCTYPE, cutting_plan)
		frappe.has_permission(DOCTYPE, ptype="read", doc=doc, throw=True)
		groups = _saved_matrix(doc)
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
		groups = []
		if lot:
			lot_payload = load_lot_items(lot)
			doc.lot = lot
			doc.item = lot_payload["item"]
			doc.production_detail = lot_payload["production_detail"]
			groups = lot_payload["groups"]
	return _serialize_editor(doc, groups)


@frappe.whitelist()
def save(
	values,
	name: str | None = None,
	submit: bool = False,
	expected_modified: str | None = None,
) -> dict:
	values = _normalize_values(values)

	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		frappe.has_permission(DOCTYPE, ptype="write", doc=doc, throw=True)
		_assert_not_stale(doc, expected_modified)
		docstatus = cint(doc.docstatus)
		if docstatus == 1:
			if sbool(submit):
				frappe.throw(_("A submitted Cutting Plan cannot be submitted again."))
			allowed = set(_allow_on_submit_fields(doc))
			denied = set(values) - allowed
			if denied:
				frappe.throw(
					_("Only Allow on Submit fields can be changed after submission: {0}.").format(
						", ".join(sorted(denied))
					)
				)
			doc.update({fieldname: values[fieldname] for fieldname in allowed if fieldname in values})
			doc.save()
			return get_editor(doc.name)
		if docstatus != 0:
			frappe.throw(_("Only Draft Cutting Plans can be edited."))
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)

	_assert_field_permissions(values)
	lot = values.get("lot")
	incoming_groups = values.get("item_details")
	if not lot:
		frappe.throw(_("Lot is required."))
	if not isinstance(incoming_groups, list) or not incoming_groups:
		frappe.throw(_("Load the Lot quantities before saving the Cutting Plan."))

	lot_doc = _get_lot(lot)
	authoritative_groups = get_items(lot) or []
	merged_groups = _merge_authoritative_matrix(authoritative_groups, incoming_groups)
	header = {
		fieldname: values.get(fieldname)
		for fieldname in EDITABLE_FIELDS - {"item_details"}
		if fieldname in values
	}
	header.update(
		{
			"lot": lot,
			"item": _doc_value(lot_doc, "item"),
			"production_detail": _doc_value(lot_doc, "production_detail"),
			"item_details": frappe.as_json(merged_groups),
		}
	)
	doc.update(header)
	if name:
		doc.save()
	else:
		doc.insert()
	if sbool(submit):
		frappe.has_permission(DOCTYPE, ptype="submit", doc=doc, throw=True)
		doc.submit()
	return get_editor(doc.name)


@frappe.whitelist()
def change_status(
	name: str,
	action: str,
	expected_modified: str | None = None,
) -> dict:
	if action not in STATUS_ACTIONS:
		frappe.throw(_("Unsupported Cutting Plan action: {0}.").format(action))
	doc = frappe.get_doc(DOCTYPE, name)
	_assert_not_stale(doc, expected_modified)

	if action == "submit":
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft Cutting Plans can be submitted."))
		frappe.has_permission(DOCTYPE, ptype="submit", doc=doc, throw=True)
		doc.submit()
		return get_editor(doc.name)
	if action == "cancel":
		if cint(doc.docstatus) != 1:
			frappe.throw(_("Only submitted Cutting Plans can be cancelled."))
		frappe.has_permission(DOCTYPE, ptype="cancel", doc=doc, throw=True)
		doc.cancel()
		return get_editor(doc.name)

	if cint(doc.docstatus) != 2:
		frappe.throw(_("Only cancelled Cutting Plans can be amended."))
	frappe.has_permission(DOCTYPE, ptype="amend", doc=doc, throw=True)
	amended = frappe.copy_doc(doc)
	amended.docstatus = 0
	amended.amended_from = doc.name
	amended.insert()
	return get_editor(amended.name)
