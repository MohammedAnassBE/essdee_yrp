"""Apply a browser patch to a stored or new IPD document, in memory only."""

import json

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt
from yrp.attribute_links import value as attribute_value

from essdee_yrp.api.duplicate import build_duplicate_values
from essdee_yrp.ipd_ui import get_complete_item_details
from essdee_yrp.merch.ipd import fields as registry

NUMERIC_TYPES = ("Int", "Check", "Float", "Percent", "Currency")
ITEM_DEFAULTS = {
	"primary_item_attribute": "primary_attribute",
	"dependent_attribute": "dependent_attribute",
	"dependent_attribute_mapping": "dependent_attribute_mapping",
	"is_cloth_item": "is_cloth_item",
}
KIND_ORDER = (registry.SCALAR, registry.TABLE, registry.LIST, registry.JSON, registry.VIRTUAL)


def load_ipd(name=None, ptype="write"):
	if not name:
		frappe.has_permission(registry.DOCTYPE, ptype="create", throw=True)
		return frappe.new_doc(registry.DOCTYPE)
	doc = frappe.get_doc(registry.DOCTYPE, name)
	doc.check_permission(ptype)
	return doc


def load_editor_ipd(name=None, duplicate_from=None):
	"""Writable IPD, or an unsaved new IPD copied from `duplicate_from` like Desk Duplicate."""
	doc = load_ipd(name, "write")
	if name or not duplicate_from:
		return doc
	values = build_duplicate_values(registry.DOCTYPE, duplicate_from)
	doc.update({key: value for key, value in values.items() if value is not None})
	return doc


def build_draft(name, values=None, ptype="write"):
	doc = load_ipd(name, ptype)
	apply_patch(doc, values or {})
	return doc


def apply_patch(doc, values: dict) -> None:
	values = dict(values or {})
	if "item" in values:
		apply_item(doc, values.pop("item"))
	reject_unknown_keys(doc, values)
	for kind in KIND_ORDER:
		for key, value in values.items():
			if registry.kind_of(key) == kind:
				APPLIERS[kind](doc, key, value)


def apply_item(doc, item):
	if not doc.is_new():
		frappe.throw(_("Item is fixed once the IPD exists. Use New version from… to copy to another item."))
	item = cstr(item).strip()
	if not item:
		frappe.throw(_("Select an Item."))
	details = get_complete_item_details(item)
	doc.item = item
	for fieldname, item_field in ITEM_DEFAULTS.items():
		doc.set(fieldname, details.get(item_field))
	doc.set(
		"item_attributes",
		[
			{"attribute": row.get("attribute"), "mapping": row.get("mapping")}
			for row in details.get("attributes") or []
		],
	)


def reject_unknown_keys(doc, values):
	for key in values:
		if key in registry.READ_ONLY:
			frappe.throw(_("{0} is read only.").format(field_label(key)))
		section = registry.section_of(key)
		if not section:
			frappe.throw(_("{0} cannot be changed here.").format(key))
		if not registry.supports_field(doc, key):
			frappe.throw(_("{0} is not part of this kind of IPD.").format(field_label(key)))


def field_label(key):
	field = registry.meta_field(key)
	return _(field.label) if field and field.label else key


def coerce(field, value):
	if value in (None, ""):
		return 0 if field.fieldtype in NUMERIC_TYPES else None
	if field.fieldtype == "Check":
		return 1 if cint(value) else 0
	if field.fieldtype == "Int":
		return cint(value)
	if field.fieldtype in ("Float", "Percent", "Currency"):
		return flt(value)
	if isinstance(value, (dict, list)):
		frappe.throw(_("{0} must be a single value.").format(_(field.label)))
	value = cstr(value)
	if field.fieldtype == "Select" and value not in (field.options or "").split("\n"):
		frappe.throw(_("{0} is not a valid {1}.").format(value, _(field.label)))
	return value


def stored_or_incoming(field, stored_raw, incoming):
	"""Keep the stored attribute-value id while the plain value is unchanged."""
	if (
		field.fieldtype == "Link"
		and field.options == registry.ATTRIBUTE_VALUE
		and stored_raw
		and incoming is not None
		and attribute_value(stored_raw) == incoming
	):
		return stored_raw
	return incoming


def apply_scalar(doc, key, value):
	field = registry.meta_field(key)
	doc.set(key, stored_or_incoming(field, doc.get(key), coerce(field, value)))


def apply_table(doc, table, rows):
	if not isinstance(rows, list):
		frappe.throw(_("{0} must be a list of rows.").format(field_label(table)))
	stored = {row.name: row for row in doc.get(table) or []}
	child_meta = frappe.get_meta(registry.row_doctype(table))
	targets = [match_row(table, stored, incoming, index) for index, incoming in enumerate(rows, start=1)]
	names = [row.name for row, _incoming in targets if row is not None]
	if len(names) != len(set(names)):
		frappe.throw(_("{0} lists a row twice.").format(field_label(table)))
	doc.set(table, [])
	for index, (stored_row, incoming) in enumerate(targets, start=1):
		row = doc.append(table, stored_row if stored_row is not None else {})
		row.idx = index
		stored_stage = row.get("in_stage") if stored_row is not None else None
		write_row(table, child_meta, row, stored_row, incoming)
		if table == "ipd_processes" and (stored_row is None or row.in_stage != stored_stage):
			row.out_stage = row.in_stage


def match_row(table, stored, incoming, index):
	if not isinstance(incoming, dict):
		frappe.throw(_("Row {0} of {1} must be an object.").format(index, field_label(table)))
	allowed = {"name", *registry.ROW_FIELDS[table], *registry.ROW_READ_ONLY.get(table, ())}
	unknown = sorted(set(incoming) - allowed)
	if unknown:
		frappe.throw(
			_("Row {0} of {1}: {2} cannot be changed here.").format(
				index, field_label(table), ", ".join(unknown)
			)
		)
	name = incoming.get("name")
	if name and name not in stored:
		frappe.throw(_("Unknown {0} row: {1}").format(field_label(table), name))
	return (stored[name] if name else None), incoming


def write_row(table, child_meta, row, stored_row, incoming):
	for fieldname in registry.ROW_READ_ONLY.get(table, ()):
		if fieldname in incoming and not same_value(
			incoming[fieldname], row.get(fieldname) if stored_row else None
		):
			frappe.throw(
				_("Row {0} of {1}: {2} is read only.").format(row.idx, field_label(table), fieldname)
			)
	for fieldname in registry.ROW_FIELDS[table]:
		if fieldname not in incoming:
			continue
		field = child_meta.get_field(fieldname)
		value = stored_or_incoming(field, row.get(fieldname), coerce(field, incoming[fieldname]))
		if (
			table == "item_attributes"
			and stored_row is not None
			and row.mapping
			and value != row.get(fieldname)
		):
			frappe.throw(
				_("Remove the {0} attribute row and add the new attribute instead.").format(
					row.get(fieldname)
				)
			)
		row.set(fieldname, value)


def same_value(incoming, stored):
	return (incoming or None) == (attribute_value(stored) or None)


def apply_list(doc, key, attributes):
	if not isinstance(attributes, list) or not all(isinstance(value, str) for value in attributes):
		frappe.throw(_("{0} must be a list of attributes.").format(field_label(key)))
	if len(set(attributes)) != len(attributes):
		frappe.throw(_("{0} lists an attribute twice.").format(field_label(key)))
	stored = {row.attribute: row for row in doc.get(key) or []}
	doc.set(key, [])
	for index, attribute in enumerate(attributes, start=1):
		row = doc.append(key, stored.get(attribute) or {"attribute": attribute})
		row.idx = index


def apply_json(doc, key, value):
	if not isinstance(value, dict):
		frappe.throw(_("{0} must be an object.").format(field_label(key)))
	blocked = registry.json_write_block(doc, key)
	if blocked:
		frappe.throw(_("{0} {1}.").format(field_label(key), _(blocked)))
	doc.set(key, value)


def apply_virtual(doc, key, value):
	VIRTUAL_APPLIERS[key](doc, value)


def ordered_combination(value, label):
	if isinstance(value, str):
		value = frappe.parse_json(value)
	if (
		not isinstance(value, dict)
		or not isinstance(value.get("attributes"), list)
		or not isinstance(value.get("values"), list)
	):
		frappe.throw(_("{0} must have attributes and values.").format(label))
	attributes = list(value["attributes"])
	rows = []
	for row in value["values"]:
		cells = row.get("val") if isinstance(row, dict) else None
		if not isinstance(cells, dict):
			frappe.throw(_("{0}: every row needs a major value and cells.").format(label))
		ordered = {attribute: cells[attribute] for attribute in attributes if attribute in cells}
		ordered.update({part: cell for part, cell in cells.items() if part not in ordered})
		rows.append({"major_attribute": row.get("major_attribute"), "val": ordered})
	return {"attributes": attributes, "values": rows}


def apply_set_item_detail(doc, value):
	if not cint(doc.get("is_set_item")):
		frappe.throw(_("Turn on Set item before sending the set combination."))
	doc.set("set_item_detail", json.dumps(ordered_combination(value, _("Set combination"))))


def apply_stiching_item_detail(doc, value):
	combination = ordered_combination(value, _("Stitching combination"))
	if combination["values"]:
		doc.set("stiching_item_detail", json.dumps(combination))


def apply_marker_groups(doc, groups):
	if not isinstance(groups, list) or not all(isinstance(group, list) for group in groups):
		frappe.throw(_("Bundle groups must be a list of panel lists."))
	rows = []
	for group in groups:
		panels = sorted(cstr(panel) for panel in group if cstr(panel))
		if panels:
			rows.append({"group_panels": ",".join(panels)})
	doc.set("cutting_marker_groups", rows)


APPLIERS = {
	registry.SCALAR: apply_scalar,
	registry.TABLE: apply_table,
	registry.LIST: apply_list,
	registry.JSON: apply_json,
	registry.VIRTUAL: apply_virtual,
}
VIRTUAL_APPLIERS = {
	"set_item_detail": apply_set_item_detail,
	"stiching_item_detail": apply_stiching_item_detail,
	"marker_groups": apply_marker_groups,
}
