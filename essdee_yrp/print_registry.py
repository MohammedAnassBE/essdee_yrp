"""Print formats exposed by the focused web workspaces.

The named formats are migrated counterparts of the production_api formats.
Documents without a custom production_api format retain Frappe's Standard
print, matching the legacy Desk print menu.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

DOCUMENT_PRINT_FORMATS = {
	"YRP Production Order": (("Production Order", "Essdee Production Order"),),
	"SD YRP Cutting Plan": (
		("Cutting Plan", "Essdee Cutting Plan"),
		("Cutting Plan Summary", "Essdee Cutting Plan Summary"),
		("Cutting Plan CCR", "Essdee Cutting Plan CCR"),
	),
	"SD YRP Cutting Order": (
		("Cutting Order", "Essdee Cutting Order"),
		("Cutting Order Summary", "Essdee Cutting Order Summary"),
		("Cutting Order CCR", "Essdee Cutting Order CCR"),
	),
	"SD YRP Cutting Marker": (("Marker Ratio", "Essdee Marker Ratio"),),
	"SD YRP Cutting LaySheet": (
		("Cutting LaySheet", "Essdee Cutting LaySheet"),
		("Cutting Movement Chart", "Essdee Cutting Movement Chart"),
		("Cutting Movement Chart 2", "Essdee Cutting Movement Chart 2"),
	),
	"SD YRP Finishing Plan Dispatch": (("Finishing Plan Dispatch", "Essdee Finishing Plan Dispatch"),),
	"SD YRP Cut Panel Movement": (
		("Cut Panel Movement", "Essdee Cut Panel Movement Print"),
	),
	"YRP Stock Entry": (
		("Stock Transfer", "Essdee Stock Transfer"),
		("Dispatch Colour Slip", "Essdee Dispatch Colour Slip"),
	),
	"YRP Stock Reconciliation": (("Standard Print", "Standard"),),
	"YRP Stock Update": (("Standard Print", "Standard"),),
	"SD YRP Lot Transfer": (("Standard Print", "Standard"),),
	"YRP Goods Received Note": (
		("Standard Print", "Standard"),
		("Rework Print", "Essdee Rework Print"),
		("Reworked Print", "Essdee Reworked Print"),
	),
	"YRP Delivery Challan": (
		("Delivery Challan", "Essdee Delivery Challan"),
		("DC", "Essdee DC"),
	),
}


def get_document_print_formats(doc):
	"""Return the legacy-equivalent print menu for a readable document."""
	if not doc or not doc.has_permission("print"):
		return []
	if doc.meta.is_submittable:
		setting = {0: "allow_print_for_draft", 2: "allow_print_for_cancelled"}.get(cint(doc.docstatus))
		if setting and not cint(frappe.db.get_single_value("Print Settings", setting)):
			return []
	return [
		{"label": label, "format": print_format}
		for label, print_format in DOCUMENT_PRINT_FORMATS.get(
			doc.doctype, (("Standard Print", "Standard"),)
		)
	]
