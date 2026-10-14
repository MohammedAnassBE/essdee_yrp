"""Install YRP stock dimensions on Essdee-owned transaction child tables.

The dimension definitions remain owned by base YRP.  This module only extends
that configured contract to Essdee transaction rows, so adding a future stock
dimension does not require another hard-coded Essdee schema change.
"""

from __future__ import annotations

import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cstr
from yrp.attribute_links import value as attribute_value
from yrp.stock.dimensions import get_stock_dimensions
from yrp.yrp.doctype.yrp_item.yrp_item import (
	_find_variant_by_attributes,
	build_variant_attributes,
)

MANAGED_FIELD_MARKER = "Managed by SD YRP from YRP Stock Dimension"

# Lot Transfer uses two explicit Lot links because a row represents a movement
# from one dimension value to another.  Every other configured dimension is a
# normal dynamic field on that row.
ESSDEE_STOCK_DIMENSION_TARGETS = {
	"SD YRP FG Stock Entry Detail": set(),
	"SD YRP Item Conversion Detail": set(),
	"SD YRP Lot Transfer Item": {"lot"},
}


def find_variant(template, args, dependent_attr=None):
	"""Return an existing normalized variant without changing Item records."""

	if isinstance(args, str):
		args = json.loads(args)
	args = {key: attribute_value(value) for key, value in (args or {}).items()}
	template_doc = frappe.get_cached_doc("Item", template)
	if not args:
		return template_doc.name if not template_doc.has_variants and not template_doc.variant_of else None
	if not template_doc.has_variants or template_doc.variant_of:
		return None
	stage = args.get(template_doc.dependent_attribute) if template_doc.dependent_attribute else None
	if stage:
		source = (
			frappe._dict(name=template, dependent_attribute_mapping=dependent_attr)
			if dependent_attr
			else template_doc
		)
		args = build_variant_attributes(args, stage, source)
	tuple_value = str(tuple(sorted((key, cstr(value)) for key, value in args.items())))
	name = frappe.db.get_value(
		"Item",
		{"variant_of": template, "item_tuple_attribute": tuple_value},
		"name",
	)
	return name or _find_variant_by_attributes(template, args)


def ensure_essdee_stock_dimension_fields():
	"""Create/update configured dimensions on Essdee stock transaction rows."""
	dimensions = get_stock_dimensions()
	custom_fields = {}

	for doctype, excluded_fields in ESSDEE_STOCK_DIMENSION_TARGETS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		meta = frappe.get_meta(doctype)
		for dimension in dimensions:
			fieldname = dimension["fieldname"]
			if fieldname in excluded_fields or meta.get_field(fieldname):
				continue
			custom_fields.setdefault(doctype, []).append(
				{
					"fieldname": fieldname,
					"fieldtype": "Link",
					"options": dimension["dimension_doctype"],
					"label": dimension["label"],
					"reqd": int(bool(dimension.get("mandatory"))),
					"insert_after": _insert_after(doctype, fieldname),
					"module": "Essdee YRP",
					"description": MANAGED_FIELD_MARKER,
				}
			)

	if custom_fields:
		create_custom_fields(custom_fields, update=True)
	_delete_orphan_fields({row["fieldname"] for row in dimensions})


def _insert_after(doctype: str, fieldname: str) -> str:
	if doctype == "SD YRP Lot Transfer Item":
		return "received_type" if fieldname != "received_type" else "warehouse"
	return "received_type" if fieldname != "received_type" else "lot"


def _delete_orphan_fields(active_fieldnames: set[str]):
	for row in frappe.get_all(
		"Custom Field",
		filters={
			"dt": ("in", list(ESSDEE_STOCK_DIMENSION_TARGETS)),
			"description": MANAGED_FIELD_MARKER,
		},
		fields=["name", "fieldname"],
	):
		if row.fieldname not in active_fieldnames:
			frappe.delete_doc("Custom Field", row.name, ignore_permissions=True)
