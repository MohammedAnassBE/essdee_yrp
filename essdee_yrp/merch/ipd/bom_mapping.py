"""Edit the values of an IPD-owned BOM attribute mapping."""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from essdee_yrp.merch.ipd.attribute_values import assert_editable
from essdee_yrp.merch.ipd.fields import DOCTYPE
from essdee_yrp.merch.ipd.payload import BOM_MAPPING, bom_mapping_context, shared_bom_mappings


def bom_row(doc, row_name):
	for row in doc.get("item_bom") or []:
		if row.name == row_name:
			if not cint(row.based_on_attribute_mapping) or not row.attribute_mapping:
				frappe.throw(
					_("Tick Based on Attribute Mapping and save the IPD before editing this mapping.")
				)
			return row
	frappe.throw(_("BOM row {0} is not part of this IPD.").format(row_name))


def locked_bom_mapping(mapping, mapping_modified):
	doc = frappe.get_doc(BOM_MAPPING, mapping, for_update=True)
	if str(doc.modified) != cstr(mapping_modified):
		frappe.throw(
			_("The BOM mapping changed after you opened it. Refresh and try again."),
			frappe.TimestampMismatchError,
		)
	return doc


def required_columns(mapping):
	"""Item-side and BOM-side attributes the mapping controller expects in every row."""
	same = {row.attribute for row in mapping.item_attributes if row.same_attribute} & {
		row.attribute for row in mapping.bom_item_attributes if row.same_attribute
	}
	return {
		"item": [row.attribute for row in mapping.item_attributes if row.attribute not in same],
		"bom": [row.attribute for row in mapping.bom_item_attributes if row.attribute not in same],
	}


def clean_rows(rows, columns):
	if not isinstance(rows, list) or not rows:
		frappe.throw(_("Add at least one mapping row."))
	groups = {}
	for position, row in enumerate(rows, start=1):
		if not isinstance(row, dict) or row.get("type") not in ("item", "bom"):
			frappe.throw(_("Mapping row {0} needs a type of item or bom.").format(position))
		if row.get("attribute") not in columns[row["type"]]:
			frappe.throw(
				_("Mapping row {0}: {1} is not a mapped attribute.").format(position, row.get("attribute"))
			)
		if not cstr(row.get("attribute_value")).strip():
			frappe.throw(_("Mapping row {0}: choose a value for {1}.").format(position, row["attribute"]))
		if row["type"] == "bom" and not flt(row.get("quantity")):
			frappe.throw(_("Mapping row {0}: the BOM quantity cannot be zero.").format(position))
		groups.setdefault(cint(row.get("index")), []).append(row)
	for index, group in groups.items():
		for kind, attributes in columns.items():
			if sorted(row["attribute"] for row in group if row["type"] == kind) != sorted(attributes):
				frappe.throw(_("Mapping line {0} must set every {1} attribute once.").format(index + 1, kind))
	return [
		{
			"index": cint(row.get("index")),
			"type": row["type"],
			"attribute": row["attribute"],
			"attribute_value": cstr(row["attribute_value"]).strip(),
			"quantity": flt(row.get("quantity")),
		}
		for row in rows
	]


def save_bom_mapping(name, row_name, rows, mapping_modified):
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	assert_editable(doc)
	row = bom_row(doc, row_name)
	if row.attribute_mapping in shared_bom_mappings(doc, [row.attribute_mapping]):
		frappe.throw(_("This BOM mapping is shared with another document and cannot be edited here."))
	mapping = locked_bom_mapping(row.attribute_mapping, mapping_modified)
	mapping.set("values", clean_rows(rows, required_columns(mapping)))
	mapping.save(ignore_permissions=True)
	frappe.clear_document_cache(BOM_MAPPING, mapping.name)
	return {"bom_mappings": {row.name: bom_mapping_context(doc)[row.name]}}
