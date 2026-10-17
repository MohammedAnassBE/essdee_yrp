import frappe
from frappe import _
from frappe.utils import cint, cstr, flt
from yrp.attribute_links import value as attribute_value
from yrp.yrp.doctype.yrp_item import yrp_item

from essdee_yrp.item_bom_attribute_mapping import get_item_bom_mapping_combinations
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


def mapping_columns(mapping):
	columns = required_columns(mapping)
	item_same = {row.attribute for row in mapping.item_attributes if row.same_attribute}
	same = [
		row.attribute
		for row in mapping.bom_item_attributes
		if row.same_attribute and row.attribute in item_same
	]
	return {**columns, "same": same, "all_same": bool(same) and not columns["item"]}


def attribute_tables(mapping):
	return {
		field: [
			{"attribute": row.attribute, "same_attribute": cint(row.same_attribute)}
			for row in mapping.get(field)
		]
		for field in ("item_attributes", "bom_item_attributes")
	}


def clean_attributes(rows, options, label):
	if not isinstance(rows, list):
		frappe.throw(_("{0} must be a list.").format(label))
	cleaned, seen = [], set()
	for row in rows:
		if not isinstance(row, dict) or row.get("attribute") not in options:
			frappe.throw(_("{0}: choose an attribute from the Item's attributes.").format(label))
		attribute = row["attribute"]
		if attribute in seen:
			frappe.throw(_("{0}: duplicate attribute {1}.").format(label, attribute))
		seen.add(attribute)
		cleaned.append(
			{"attribute": attribute, "same_attribute": cint(bool(cint(row.get("same_attribute"))))}
		)
	return cleaned


def item_attribute_rows(item):
	"""Resolve Item options under the caller's IPD permission gate."""
	return frappe.get_cached_doc("Item", yrp_item.get_parent_item(item)).get("attributes") or []


def item_attribute_options(item):
	return [row.attribute for row in item_attribute_rows(item)]


def set_attribute_tables(mapping, item, item_attributes, bom_item_attributes):
	if item_attributes is None and bom_item_attributes is None:
		return
	for field, rows, source, label in (
		("item_attributes", item_attributes, item, _("Item Attributes")),
		("bom_item_attributes", bom_item_attributes, mapping.bom_item, _("BOM Item Attributes")),
	):
		mapping.set(field, clean_attributes(rows, item_attribute_options(source), label))


def get_bom_mapping(name, row_name, item_attributes=None, bom_item_attributes=None):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	row = bom_row(doc, row_name)
	mapping = frappe.get_doc(BOM_MAPPING, row.attribute_mapping)
	set_attribute_tables(mapping, doc.item, item_attributes, bom_item_attributes)
	columns = mapping_columns(mapping)
	bom_attributes = item_attribute_rows(mapping.bom_item)
	bom_values = {
		row.attribute: yrp_item._mapping_values(row)
		for row in bom_attributes
		if row.attribute in columns["bom"]
	}
	combinations = get_item_bom_mapping_combinations(name, doc.item, columns["item"], columns["bom"])
	return {
		"mapping": mapping.name,
		"mapping_modified": str(mapping.modified),
		"item": doc.item,
		"bom_item": mapping.bom_item,
		"bom_uom": mapping.bom_uom or frappe.get_cached_value("Item", mapping.bom_item, "stock_uom"),
		**attribute_tables(mapping),
		"item_attribute_options": item_attribute_options(doc.item),
		"bom_attribute_options": [row.attribute for row in bom_attributes],
		"columns": columns,
		"bom_values": {
			attribute: bom_values.get(attribute) or yrp_item.get_global_attribute_values(attribute)
			for attribute in columns["bom"]
		},
		"combinations": [
			{attribute: combination[f"item_{attribute}"] for attribute in columns["item"]}
			for combination in combinations
		],
		"values": [
			{
				"index": value.index,
				"type": value.type,
				"attribute": value.attribute,
				"attribute_value": attribute_value(value.attribute_value),
				"quantity": value.quantity,
			}
			for value in mapping.get("values")
		],
		"is_shared": mapping.name in shared_bom_mappings(doc, [mapping.name]),
	}


def clean_rows(rows, columns, all_same=False):
	if isinstance(rows, list) and not rows and all_same:
		return []
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
		if not flt(row.get("quantity")):
			label = (
				_("the BOM quantity cannot be zero") if row["type"] == "bom" else _("Quantity cannot be zero")
			)
			frappe.throw(_("Mapping row {0}: {1}.").format(position, label))
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


def save_bom_mapping(name, row_name, rows, mapping_modified, item_attributes=None, bom_item_attributes=None):
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	assert_editable(doc)
	row = bom_row(doc, row_name)
	if row.attribute_mapping in shared_bom_mappings(doc, [row.attribute_mapping]):
		frappe.throw(_("This BOM mapping is shared with another document and cannot be edited here."))
	mapping = locked_bom_mapping(row.attribute_mapping, mapping_modified)
	set_attribute_tables(mapping, doc.item, item_attributes, bom_item_attributes)
	columns = mapping_columns(mapping)
	mapping.set("values", clean_rows(rows, required_columns(mapping), columns["all_same"]))
	mapping.save(ignore_permissions=True)
	frappe.clear_document_cache(BOM_MAPPING, mapping.name)
	return {"bom_mappings": {row.name: bom_mapping_context(doc)[row.name]}}
