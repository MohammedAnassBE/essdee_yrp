"""Cutting Order editor and routed workspace services for ``/web``."""

from __future__ import annotations

import json
from copy import deepcopy

import frappe
from frappe import _
from frappe.utils import cint, flt, sbool
from yrp.utils import update_if_string_instance

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order.sd_yrp_cutting_order import (
	get_cutting_order_detail_data,
	get_cutting_order_planned_vs_actual,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_ipd_settings.sd_yrp_ipd_settings import get_colour_attribute
from essdee_yrp.print_registry import get_document_print_formats

DOCTYPE = "SD YRP Cutting Order"
DETAIL_DOCTYPE = "SD YRP Cutting Order Detail"
EDITABLE_FIELDS = {
	"cutting_order_detail",
	"cutting_location",
	"maximum_no_of_plys",
	"maximum_allow_percent",
	"item_details",
}
STATUS_ACTIONS = {"submit", "cancel", "amend"}


def _parse_json(value, fallback):
	if value in (None, ""):
		return deepcopy(fallback)
	if isinstance(value, (dict, list)):
		return deepcopy(value)
	return frappe.parse_json(value)


def _doc_value(doc, fieldname, default=None):
	value = getattr(doc, fieldname, None)
	if value is not None and not callable(value):
		return value
	return doc.get(fieldname, default) if hasattr(doc, "get") else default


def _assert_not_stale(doc, expected_modified=None):
	if expected_modified and str(_doc_value(doc, "modified")) != str(expected_modified):
		frappe.throw(
			_("{0} changed after you opened it. Refresh and try again.").format(doc.name),
			frappe.TimestampMismatchError,
		)


def _normalize_order_values(values):
	values = _parse_json(values, {})
	if not isinstance(values, dict):
		frappe.throw(_("Cutting Order values must be an object."))
	unknown = set(values) - EDITABLE_FIELDS
	if unknown:
		frappe.throw(
			_("These Cutting Order fields cannot be changed here: {0}.").format(
				", ".join(sorted(unknown))
			)
		)
	return values


def _build_detail_matrix(detail):
	sizes = list(detail.get("sizes") or [])
	rows = detail.get("items") if detail.get("is_set_item") else [
		{"colour": colour} for colour in (detail.get("colours") or [])
	]
	colour_attribute = get_colour_attribute()
	items = []
	for index, row in enumerate(rows or []):
		attributes = {colour_attribute: row.get("colour")}
		item_keys = {"major_colour": row.get("major_colour") or row.get("colour")}
		if detail.get("is_set_item"):
			attributes["Part"] = row.get("part")
			item_keys["major_part"] = row.get("part")
		items.append(
			{
				"_row_key": f"g0:r{index}",
				"name": detail.get("item"),
				"attributes": attributes,
				"item_keys": item_keys,
				"primary_attribute": "Size",
				"values": {size: {"qty": 0} for size in sizes},
				"total_qty": 0,
			}
		)
	return [
		{
			"attributes": [colour_attribute] + (["Part"] if detail.get("is_set_item") else []),
			"primary_attribute": "Size",
			"primary_attribute_values": sizes,
			"is_set_item": bool(detail.get("is_set_item")),
			"items": items,
			"size_wise_total": {size: 0 for size in sizes},
			"total_sum": 0,
		}
	]


def _quantity(value, key, size):
	if isinstance(value, dict):
		value = value.get("qty")
	try:
		quantity = float(value or 0)
	except (TypeError, ValueError):
		frappe.throw(_("Enter a valid quantity for row {0}, size {1}.").format(key, size))
	if quantity < 0:
		frappe.throw(_("Quantity cannot be negative for row {0}, size {1}.").format(key, size))
	return flt(quantity)


def _merge_order_matrix(authoritative_groups, incoming_groups):
	authoritative = deepcopy(authoritative_groups or [])
	expected = {
		row["_row_key"]: row
		for group in authoritative
		for row in (group.get("items") or [])
	}
	received = {}
	for group in _parse_json(incoming_groups, []):
		for row in group.get("items") or []:
			key = row.get("_row_key")
			if key not in expected:
				frappe.throw(_("The Cutting Order contains an unknown item row."))
			if key in received:
				frappe.throw(_("The Cutting Order contains a duplicate item row: {0}.").format(key))
			for fieldname in ("name", "attributes", "item_keys"):
				if fieldname in row and row[fieldname] != expected[key].get(fieldname):
					frappe.throw(_("Item identity changed for row {0}. Reload the Detail and try again.").format(key))
			received[key] = row
	if set(received) != set(expected):
		frappe.throw(_("The Cutting Order item rows changed. Reload the Detail and try again."))

	for group in authoritative:
		totals = {size: 0.0 for size in group.get("primary_attribute_values") or []}
		group_total = 0.0
		for row in group.get("items") or []:
			key = row["_row_key"]
			incoming_values = received[key].get("values") or {}
			if set(incoming_values) != set(row.get("values") or {}):
				frappe.throw(_("Sizes changed for row {0}. Reload the Detail and try again.").format(key))
			row_total = 0.0
			for size in row.get("values") or {}:
				quantity = _quantity(incoming_values[size], key, size)
				row["values"][size] = {"qty": quantity}
				totals[size] += quantity
				row_total += quantity
			row["total_qty"] = row_total
			group_total += row_total
		group["size_wise_total"] = totals
		group["total_sum"] = group_total
	return authoritative


def _overlay_native_quantities(matrix, native):
	items = (native or {}).get("items") or []
	by_identity = {}
	for row in items:
		key = (row.get("colour"), row.get("part"), row.get("major_colour") or row.get("colour"))
		by_identity[key] = row.get("quantities") or {}
	colour_attribute = get_colour_attribute()
	for row in matrix[0].get("items") or []:
		attrs = row.get("attributes") or {}
		keys = row.get("item_keys") or {}
		colour = attrs.get(colour_attribute)
		key = (colour, attrs.get("Part"), keys.get("major_colour") or colour)
		quantities = by_identity.get(key, {})
		for size in row.get("values") or {}:
			row["values"][size] = {"qty": flt(quantities.get(size))}
	return _merge_order_matrix(matrix, matrix)


def _matrix_to_native(matrix, detail):
	rows = []
	colour_attribute = get_colour_attribute()
	for row in matrix[0].get("items") or []:
		attributes = row.get("attributes") or {}
		item_keys = row.get("item_keys") or {}
		entry = {
			"colour": attributes.get(colour_attribute),
			"quantities": {
				size: flt(value.get("qty") if isinstance(value, dict) else value)
				for size, value in (row.get("values") or {}).items()
			},
		}
		if detail.get("is_set_item"):
			entry["part"] = attributes.get("Part")
			entry["major_colour"] = item_keys.get("major_colour") or attributes.get(colour_attribute)
		rows.append(entry)
	return {
		"is_set_item": bool(detail.get("is_set_item")),
		"sizes": list(detail.get("sizes") or []),
		"colours": list(detail.get("colours") or []),
		"parts": list(detail.get("parts") or []),
		"items": rows,
	}


def _permission_flags(doc=None):
	docstatus = cint(_doc_value(doc, "docstatus", 0)) if doc is not None else None

	def allowed(ptype, record_sensitive=True):
		kwargs = {"ptype": ptype}
		if doc is not None and record_sensitive:
			kwargs["doc"] = doc
		return bool(frappe.has_permission(DOCTYPE, **kwargs))

	flags = {
		"can_read": allowed("read"),
		"can_create": allowed("create", False),
		"can_write": allowed("write"),
		"can_submit": allowed("submit"),
		"can_cancel": allowed("cancel"),
		"can_amend": allowed("amend"),
		"can_print": allowed("print"),
	}
	if doc is not None:
		flags.update(
			can_write=bool(docstatus == 0 and flags["can_write"]),
			can_submit=bool(docstatus == 0 and flags["can_submit"]),
			can_cancel=bool(docstatus == 1 and flags["can_cancel"]),
			can_amend=bool(docstatus == 2 and flags["can_amend"]),
		)
	else:
		flags.update(can_write=False, can_cancel=False, can_amend=False)
	return flags


def _record(doc):
	return {
		"name": _doc_value(doc, "name"),
		"docstatus": cint(_doc_value(doc, "docstatus", 0)),
		"modified": _doc_value(doc, "modified"),
		"cutting_order_detail": _doc_value(doc, "cutting_order_detail"),
		"status": _doc_value(doc, "co_status") or "Draft",
		"cutting_location": _doc_value(doc, "cutting_location"),
		"item": _doc_value(doc, "item"),
		"is_set_item": cint(_doc_value(doc, "is_set_item", 0)),
		"lay_no": cint(_doc_value(doc, "lay_no", 0)),
		"maximum_no_of_plys": _doc_value(doc, "maximum_no_of_plys"),
		"maximum_allow_percent": _doc_value(doc, "maximum_allow_percent"),
		"cutting_start_date": _doc_value(doc, "cutting_start_date"),
		"cutting_end_date": _doc_value(doc, "cutting_end_date"),
	}


@frappe.whitelist()
def get_order_editor(cutting_order: str | None = None, cutting_order_detail: str | None = None):
	if cutting_order:
		doc = frappe.get_doc(DOCTYPE, cutting_order)
		frappe.has_permission(DOCTYPE, ptype="read", doc=doc, throw=True)
		saved_detail = doc.cutting_order_detail
		cutting_order_detail = cutting_order_detail or saved_detail
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
		saved_detail = None

	detail = None
	matrix = []
	if cutting_order_detail:
		detail = get_cutting_order_detail_data(cutting_order_detail)
		matrix = _build_detail_matrix(detail)
		if cutting_order and cutting_order_detail == saved_detail:
			matrix = _overlay_native_quantities(
				matrix,
				_parse_json(_doc_value(doc, "items_json", "{}"), {}),
			)
	return {
		"record": _record(doc),
		"detail": detail,
		"matrix": {"groups": matrix},
		"permissions": _permission_flags(doc if cutting_order else None),
		"options": {"cutting_locations": ["Machine Cutting", "Manual Cutting"]},
	}


@frappe.whitelist()
def save_order(values, name=None, submit=False, expected_modified=None):
	values = _normalize_order_values(values)
	detail_name = values.get("cutting_order_detail")
	if not detail_name:
		frappe.throw(_("Cutting Order Detail is required."))
	incoming = values.get("item_details")
	if not isinstance(incoming, list) or not incoming:
		frappe.throw(_("Load the Cutting Order Detail quantities before saving."))
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		frappe.has_permission(DOCTYPE, ptype="write", doc=doc, throw=True)
		_assert_not_stale(doc, expected_modified)
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft Cutting Orders can be edited."))
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)

	detail = get_cutting_order_detail_data(detail_name)
	merged = _merge_order_matrix(_build_detail_matrix(detail), incoming)
	doc.update(
		{
			"cutting_order_detail": detail_name,
			"cutting_location": values.get("cutting_location"),
			"maximum_no_of_plys": values.get("maximum_no_of_plys"),
			"maximum_allow_percent": values.get("maximum_allow_percent"),
			"item": detail.get("item"),
			"is_set_item": cint(detail.get("is_set_item")),
			"items_json": frappe.as_json(_matrix_to_native(merged, detail)),
		}
	)
	if name:
		doc.save()
	else:
		doc.insert()
	if sbool(submit):
		frappe.has_permission(DOCTYPE, ptype="submit", doc=doc, throw=True)
		doc.submit()
	return get_order_editor(doc.name)


@frappe.whitelist()
def change_order_status(name, action, expected_modified=None):
	if action not in STATUS_ACTIONS:
		frappe.throw(_("Unsupported Cutting Order action: {0}.").format(action))
	doc = frappe.get_doc(DOCTYPE, name)
	_assert_not_stale(doc, expected_modified)
	if action == "submit":
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only Draft Cutting Orders can be submitted."))
		frappe.has_permission(DOCTYPE, ptype="submit", doc=doc, throw=True)
		doc.submit()
		return get_order_editor(doc.name)
	if action == "cancel":
		if cint(doc.docstatus) != 1:
			frappe.throw(_("Only submitted Cutting Orders can be cancelled."))
		frappe.has_permission(DOCTYPE, ptype="cancel", doc=doc, throw=True)
		doc.cancel()
		return get_order_editor(doc.name)
	if cint(doc.docstatus) != 2:
		frappe.throw(_("Only cancelled Cutting Orders can be amended."))
	frappe.has_permission(DOCTYPE, ptype="amend", doc=doc, throw=True)
	amended = frappe.copy_doc(doc)
	amended.docstatus = 0
	amended.amended_from = doc.name
	amended.insert()
	return get_order_editor(amended.name)


def _related_permissions(doctype):
	return {
		"can_read": bool(frappe.has_permission(doctype, ptype="read")),
		"can_create": bool(frappe.has_permission(doctype, ptype="create")),
	}


def _overview_detail(doc, fieldname, label):
	field = doc.meta.get_field(fieldname)
	return {
		"fieldname": fieldname,
		"label": label,
		"fieldtype": field.fieldtype if field else "Data",
		"options": field.options if field else None,
		"value": _doc_value(doc, fieldname),
	}


@frappe.whitelist()
def get_order_workspace(cutting_order):
	doc = frappe.get_doc(DOCTYPE, cutting_order)
	frappe.has_permission(DOCTYPE, ptype="read", doc=doc, throw=True)
	permissions = _permission_flags(doc)
	marker_permissions = _related_permissions("SD YRP Cutting Marker")
	laysheet_permissions = _related_permissions("SD YRP Cutting LaySheet")
	markers = []
	if marker_permissions["can_read"]:
		markers = frappe.get_list(
			"SD YRP Cutting Marker",
			filters={"cutting_order": cutting_order},
			fields=["name", "marker_name", "length", "width", "required_piece_weight", "calculated_parts", "docstatus", "modified"],
			order_by="modified desc",
			limit_page_length=500,
		)
	laysheets = []
	if laysheet_permissions["can_read"]:
		laysheets = frappe.get_list(
			"SD YRP Cutting LaySheet",
			filters={"cutting_order": cutting_order},
			fields=["name", "lay_no", "cutting_marker", "marker_name", "status", "bundle_generated_date", "printed_time", "docstatus", "modified"],
			order_by="modified desc",
			limit_page_length=500,
		)
	is_submitted = cint(doc.docstatus) == 1
	can_run = bool(is_submitted and permissions["can_read"] and frappe.has_permission(DOCTYPE, ptype="write", doc=doc))
	return {
		"record": _record(doc),
		"details": [
			_overview_detail(doc, fieldname, label)
			for fieldname, label in (
				("cutting_order_detail", "Cutting Order Detail"),
				("item", "Item"),
				("maximum_no_of_plys", "Maximum No of Plys"),
				("maximum_allow_percent", "Maximum Allow Percent"),
				("cutting_location", "Cutting Location"),
				("lay_no", "Lay No"),
			)
		],
		"matrix": {"groups": get_order_editor(cutting_order)["matrix"]["groups"]},
		"completed_items": update_if_string_instance(_doc_value(doc, "completed_items_json")),
		"incomplete_items": update_if_string_instance(_doc_value(doc, "incomplete_items_json")),
		"planned_detail": get_cutting_order_planned_vs_actual(cutting_order),
		"markers": markers,
		"laysheets": laysheets,
		"permissions": {
			**permissions,
			"can_read_marker": marker_permissions["can_read"],
			"can_create_marker": bool(is_submitted and marker_permissions["can_create"]),
			"can_read_laysheet": laysheet_permissions["can_read"],
			"can_create_laysheet": bool(is_submitted and laysheet_permissions["can_create"]),
		},
		"actions": {
			"can_calculate_laysheets": can_run,
			"can_get_completed": bool(is_submitted and permissions["can_read"]),
			"can_update_completed": can_run,
		},
		"print_formats": get_document_print_formats(doc),
	}


@frappe.whitelist()
def update_completed_items(cutting_order, completed_items, expected_modified=None):
	"""Update completion flags without accepting browser-owned quantities or identities."""
	doc = frappe.get_doc(DOCTYPE, cutting_order)
	frappe.has_permission(DOCTYPE, ptype="write", doc=doc, throw=True)
	_assert_not_stale(doc, expected_modified)
	if cint(doc.docstatus) != 1:
		frappe.throw(_("Only submitted Cutting Orders can update completed items."))

	current = update_if_string_instance(_doc_value(doc, "completed_items_json"))
	incoming = _parse_json(completed_items, {})
	current_groups = current if isinstance(current, list) else [current]
	incoming_groups = incoming if isinstance(incoming, list) else [incoming]
	if len(current_groups) != len(incoming_groups):
		frappe.throw(_("The completed quantity structure changed. Reload and try again."))

	for group_index, current_group in enumerate(current_groups):
		incoming_group = incoming_groups[group_index]
		if not isinstance(current_group, dict) or not isinstance(incoming_group, dict):
			frappe.throw(_("The completed quantity structure is invalid. Reload and try again."))
		current_rows = current_group.get("items") or []
		incoming_rows = incoming_group.get("items") or []
		if len(current_rows) != len(incoming_rows):
			frappe.throw(_("The completed quantity rows changed. Reload and try again."))
		for row_index, current_row in enumerate(current_rows):
			current_row["completed"] = bool(incoming_rows[row_index].get("completed"))

	doc.completed_items_json = frappe.as_json(
		current_groups if isinstance(current, list) else current_groups[0]
	)
	doc.save()
	return get_order_workspace(doc.name)
