"""Permission-checked web editor for Cutting Order Detail."""

from __future__ import annotations

import json
from copy import deepcopy

import frappe
from frappe import _
from frappe.utils import cint, sbool
from yrp.attribute_links import value as _attribute_value
from yrp.attribute_values import get_mapping_document

from essdee_yrp.ipd_ui import fetch_combination_items, get_new_combination
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_order_detail.sd_yrp_cutting_order_detail import (
	get_co_new_combination,
)


DOCTYPE = "SD YRP Cutting Order Detail"
EDITABLE_FIELDS = {
	"item",
	"attribute_no",
	"is_set_item",
	"set_item_attribute",
	"major_attribute_value",
	"major_panel_value",
	"is_same_colour",
	"attributes",
	"colours",
	"panels",
	"cloth_details",
	"set_item_combination",
	"stiching_combination",
}


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


def _permission_flags(doc=None):
	def allowed(ptype, record_sensitive=True):
		kwargs = {"ptype": ptype}
		if doc is not None and record_sensitive:
			kwargs["doc"] = doc
		return bool(frappe.has_permission(DOCTYPE, **kwargs))

	return {
		"can_read": allowed("read"),
		"can_create": allowed("create", False),
		"can_write": bool(doc is not None and allowed("write")),
	}


def _normalize_values(values):
	values = _parse_json(values, {})
	if not isinstance(values, dict):
		frappe.throw(_("Cutting Order Detail values must be an object."))
	unknown = set(values) - EDITABLE_FIELDS
	if unknown:
		frappe.throw(
			_("These Cutting Order Detail fields cannot be changed here: {0}.").format(
				", ".join(sorted(unknown))
			)
		)
	return values


def _merge_named_rows(
	existing_rows,
	incoming_rows,
	allowed_fields,
	immutable_fields=(),
	server_owned_new_fields=(),
):
	"""Preserve known child names; new browser rows arrive without a name."""

	existing = {
		_doc_value(row, "name"): row
		for row in (existing_rows or [])
		if _doc_value(row, "name")
	}
	seen = set()
	merged = []
	for incoming in _parse_json(incoming_rows, []):
		key = incoming.get("_row_key")
		if key:
			if key not in existing:
				frappe.throw(_("The editor contains an unknown child row."))
			if key in seen:
				frappe.throw(_("The editor contains a duplicate child row: {0}.").format(key))
			seen.add(key)
			row = {"name": key}
			for fieldname in immutable_fields:
				if fieldname in incoming and incoming.get(fieldname) != _doc_value(existing[key], fieldname):
					frappe.throw(
						_("The identity of child row {0} cannot be changed.").format(key)
					)
				row[fieldname] = _doc_value(existing[key], fieldname)
		else:
			for fieldname in server_owned_new_fields:
				if incoming.get(fieldname):
					frappe.throw(_("The server assigns {0} for new child rows.").format(fieldname))
			row = {}
		for fieldname in allowed_fields:
			if key and fieldname in immutable_fields:
				continue
			if not key and fieldname in server_owned_new_fields:
				continue
			if fieldname in incoming:
				row[fieldname] = incoming.get(fieldname)
		merged.append(row)
	return merged


def _serialize_named_rows(rows, fields):
	return [
		{
			"_row_key": _doc_value(row, "name") or f"new:{index}",
			**{fieldname: _attribute_value(_doc_value(row, fieldname)) for fieldname in fields},
		}
		for index, row in enumerate(rows or [])
	]


def _attribute_projection(doc):
	attributes = []
	for index, row in enumerate(_doc_value(doc, "item_attributes", []) or []):
		values = []
		mapping = _doc_value(row, "mapping")
		if mapping:
			mapping_doc = get_mapping_document(mapping, cached=True)
			values = [
				_attribute_value(_doc_value(entry, "attribute_value"))
				for entry in (_doc_value(mapping_doc, "values", []) or [])
			]
		attributes.append(
			{
				"_row_key": _doc_value(row, "name") or f"new:{index}",
				"attribute": _doc_value(row, "attribute"),
				"mapping": mapping,
				"values": values,
			}
		)
	return attributes


def _combination_projection(rows):
	if not rows:
		return {"attributes": [], "values": []}
	return fetch_combination_items(rows)


def _mapping_for(doc, attribute):
	for row in (_doc_value(doc, "item_attributes", []) or []):
		if _doc_value(row, "attribute") == attribute:
			return _doc_value(row, "mapping")
	return None


def _colour_rows(doc):
	return [
		{"attribute_value": _attribute_value(_doc_value(row, "attribute_value"))}
		for row in (_doc_value(doc, "attribute_values", []) or [])
	]


def _merge_authoritative_combination(expected, incoming, label):
	"""Accept only values for the server-derived combination coordinates."""

	expected = deepcopy(expected or {"attributes": [], "values": []})
	incoming = _parse_json(incoming, {})
	if not incoming or not incoming.get("values"):
		return expected
	expected_attributes = list(expected.get("attributes") or [])
	if list(incoming.get("attributes") or expected_attributes) != expected_attributes:
		frappe.throw(_("{0} attributes changed. Regenerate the combinations and try again.").format(label))
	expected_rows = {
		str(row.get("major_attribute")): row
		for row in (expected.get("values") or [])
	}
	received_rows = {}
	for row in incoming.get("values") or []:
		key = str(row.get("major_attribute"))
		if key not in expected_rows or key in received_rows:
			frappe.throw(_("{0} contains an unknown or duplicate major value.").format(label))
		values = row.get("val") or {}
		if set(values) != set(expected_attributes):
			frappe.throw(_("{0} columns changed. Regenerate the combinations and try again.").format(label))
		received_rows[key] = values
	if set(received_rows) != set(expected_rows):
		frappe.throw(_("{0} rows changed. Regenerate the combinations and try again.").format(label))
	for key, row in expected_rows.items():
		row["val"] = {attribute: received_rows[key][attribute] for attribute in expected_attributes}
	return expected


def _save_authoritative_combinations(doc, values):
	colours = _colour_rows(doc)
	if _doc_value(doc, "is_set_item"):
		mapping = _mapping_for(doc, _doc_value(doc, "set_item_attribute"))
		major = _attribute_value(_doc_value(doc, "major_attribute_value"))
		if not mapping or not major:
			frappe.throw(_("Set Item Attribute and Major Attribute Value are required."))
		expected = get_new_combination(mapping, colours, major)
		merged = _merge_authoritative_combination(
			expected,
			values.get("set_item_combination"),
			_("Set Item Combination"),
		)
		doc.set_item_detail = frappe.as_json(merged)
		doc.save()
		doc.reload()

	panel_mapping = _mapping_for(doc, _doc_value(doc, "stiching_attribute"))
	major_panel = _attribute_value(_doc_value(doc, "major_panel_value"))
	if panel_mapping and major_panel and colours:
		expected = get_co_new_combination(
			panel_mapping,
			colours,
			major_panel,
			_doc_value(doc, "is_same_colour", 0),
			_doc_value(doc, "name"),
		)
		merged = _merge_authoritative_combination(
			expected,
			values.get("stiching_combination"),
			_("Panel Combination"),
		)
		doc.stiching_item_detail = frappe.as_json(merged)
		doc.save()


def _serialize_detail(doc):
	try:
		cloth_details = json.loads(_doc_value(doc, "cloth_detail_json", "[]") or "[]")
	except (json.JSONDecodeError, TypeError):
		cloth_details = []
	return {
		"record": {
			"name": _doc_value(doc, "name"),
			"modified": _doc_value(doc, "modified"),
			"item": _doc_value(doc, "item"),
			"version": cint(_doc_value(doc, "version", 0)),
			"primary_attribute": _doc_value(doc, "primary_attribute"),
			"packing_attribute": _doc_value(doc, "packing_attribute"),
			"stiching_attribute": _doc_value(doc, "stiching_attribute"),
			"attribute_no": cint(_doc_value(doc, "attribute_no", 0)),
			"is_set_item": cint(_doc_value(doc, "is_set_item", 0)),
			"set_item_attribute": _doc_value(doc, "set_item_attribute"),
			"major_attribute_value": _attribute_value(_doc_value(doc, "major_attribute_value")),
			"major_panel_value": _attribute_value(_doc_value(doc, "major_panel_value")),
			"is_same_colour": cint(_doc_value(doc, "is_same_colour", 0)),
		},
		"attributes": _attribute_projection(doc),
		"colours": _serialize_named_rows(
			_doc_value(doc, "attribute_values", []),
			("attribute_value",),
		),
		"panels": _serialize_named_rows(
			_doc_value(doc, "stiching_item_details", []),
			("stiching_attribute_value", "set_item_attribute_value", "quantity", "is_default"),
		),
		"cloth_details": cloth_details,
		"set_item_combination": _combination_projection(
			_doc_value(doc, "set_item_combination_details", [])
		),
		"stiching_combination": _combination_projection(
			_doc_value(doc, "stiching_item_combination_details", [])
		),
		"permissions": _permission_flags(doc if _doc_value(doc, "name") else None),
	}


def _apply_new_defaults(doc):
	settings = frappe.get_cached_doc("SD YRP IPD Settings")
	doc.primary_attribute = settings.default_primary_attribute
	doc.packing_attribute = settings.default_packing_attribute
	doc.stiching_attribute = settings.default_stitching_attribute
	doc.set_item_attribute = settings.default_set_item_attribute


@frappe.whitelist()
def get_detail_editor(name: str | None = None, item: str | None = None):
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		frappe.has_permission(DOCTYPE, ptype="read", doc=doc, throw=True)
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
		_apply_new_defaults(doc)
		if item:
			doc.item = item
	return _serialize_detail(doc)


def _update_attribute_mappings(doc, incoming_attributes):
	by_attribute = {row.attribute: row for row in (_doc_value(doc, "item_attributes", []) or [])}
	for incoming in incoming_attributes or []:
		attribute = incoming.get("attribute")
		row = by_attribute.get(attribute)
		if not row or not row.mapping or "values" not in incoming:
			continue
		mapping = get_mapping_document(row.mapping)
		mapping.check_permission("write")
		mapping.set("values", [])
		for value in incoming.get("values") or []:
			mapping.append("values", {"attribute_value": value})
		mapping.save()


@frappe.whitelist()
def save_detail(values, name: str | None = None, expected_modified: str | None = None):
	values = _normalize_values(values)
	if not values.get("item"):
		frappe.throw(_("Item is required."))
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		frappe.has_permission(DOCTYPE, ptype="write", doc=doc, throw=True)
		_assert_not_stale(doc, expected_modified)
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)

	attributes = _merge_named_rows(
		_doc_value(doc, "item_attributes", []),
		values.get("attributes") or [],
		("attribute", "mapping"),
		("attribute", "mapping"),
		("mapping",),
	)
	colours = _merge_named_rows(
		_doc_value(doc, "attribute_values", []),
		values.get("colours") or [],
		("attribute_value",),
	)
	panels = _merge_named_rows(
		_doc_value(doc, "stiching_item_details", []),
		values.get("panels") or [],
		("stiching_attribute_value", "set_item_attribute_value", "quantity", "is_default"),
	)
	header = {
		fieldname: values.get(fieldname)
		for fieldname in (
			"item",
			"attribute_no",
			"is_set_item",
			"set_item_attribute",
			"major_attribute_value",
			"major_panel_value",
			"is_same_colour",
		)
		if fieldname in values
	}
	header.update(
		{
			"item_attributes": attributes,
			"attribute_values": colours,
			"stiching_item_details": panels,
			"cloth_detail_json": frappe.as_json(values.get("cloth_details") or []),
		}
	)
	doc.update(header)
	if name:
		_update_attribute_mappings(doc, values.get("attributes") or [])
		doc.save()
	else:
		doc.insert()
		_update_attribute_mappings(doc, values.get("attributes") or [])
	doc.reload()
	_save_authoritative_combinations(doc, values)
	return get_detail_editor(doc.name)
