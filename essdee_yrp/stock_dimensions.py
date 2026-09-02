"""Install YRP stock dimensions on Essdee-owned transaction child tables.

The dimension definitions remain owned by base YRP.  This module only extends
that configured contract to Essdee transaction rows, so adding a future stock
dimension does not require another hard-coded Essdee schema change.
"""

from __future__ import annotations

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from yrp.stock.dimensions import get_stock_dimensions


MANAGED_FIELD_MARKER = "Managed by SD YRP from YRP Stock Dimension"

# Lot Transfer uses two explicit Lot links because a row represents a movement
# from one dimension value to another.  Every other configured dimension is a
# normal dynamic field on that row.
ESSDEE_STOCK_DIMENSION_TARGETS = {
	'SD YRP FG Stock Entry Detail': set(),
	'SD YRP Item Conversion Detail': set(),
	'SD YRP Lot Transfer Item': {"lot"},
}


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
	if doctype == 'SD YRP Lot Transfer Item':
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
