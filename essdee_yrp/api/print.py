"""Desk-compatible print choices for web documents."""

import frappe
from frappe.utils import cint

from essdee_yrp.print_helpers import get_dc_grn_letter_head


def order_print_formats(records, default_format="", enable_raw_printing=False):
	"""Build the Desk list, moving an available default to the front.

	Desk's meta.get_print_formats ends up listing formats in descending name order.
	"""
	names = sorted({
		row["name"] for row in records
		if row["name"] != "Standard"
		and not cint(row.get("disabled"))
		and row.get("print_format_type") != "JS"
		and (cint(enable_raw_printing) or not cint(row.get("raw_printing")))
	}, key=str.casefold, reverse=True)
	formats = ["Standard", *names]
	if default_format and default_format != "Standard" and default_format in formats:
		formats.remove(default_format)
		formats.insert(0, default_format)
	return formats


def get_desk_print_formats(doctype):
	return _get_print_format_options(doctype)["formats"]


def _get_print_format_options(doctype):
	meta = frappe.get_meta(doctype)
	records = frappe.get_all(
		"Print Format",
		filters={"doc_type": doctype, "disabled": 0},
		fields=["name", "print_format_type", "raw_printing", "disabled"],
		order_by="name asc",
	)
	formats = order_print_formats(
		records,
		meta.default_print_format,
		frappe.db.get_single_value("Print Settings", "enable_raw_printing"),
	)
	return {
		"formats": formats,
		"raw_formats": [row["name"] for row in records if row["name"] in formats and cint(row.get("raw_printing"))],
	}


def get_print_restriction(doc):
	"""Return the Print Settings restriction, if this document has one."""
	if doc.meta.is_submittable:
		setting = {0: "allow_print_for_draft", 2: "allow_print_for_cancelled"}.get(cint(doc.docstatus))
		if setting and not cint(frappe.db.get_single_value("Print Settings", setting)):
			state = "draft" if cint(doc.docstatus) == 0 else "cancelled"
			return f"Printing {state} documents is disabled in Print Settings."
	return ""


def resolve_default_letter_head(letter_heads, document_letter_head, default_letter_head):
	if document_letter_head in letter_heads:
		return document_letter_head
	return default_letter_head if default_letter_head in letter_heads else ""


@frappe.whitelist()
def get_print_options(doctype, name):
	doc = frappe.get_doc(doctype, name)
	frappe.has_permission(doctype, "print", doc, throw=True)
	if restriction := get_print_restriction(doc):
		frappe.throw(restriction)

	format_options = _get_print_format_options(doctype)
	formats = format_options["formats"]
	default_format = frappe.get_meta(doctype).default_print_format
	letter_heads = frappe.get_all(
		"Letter Head", filters={"disabled": 0}, pluck="name", order_by="name asc"
	)
	document_letter_head = (
		get_dc_grn_letter_head(doc) if doc.doctype == "YRP Delivery Challan" else doc.get("letter_head")
	)
	default_letter_head = None
	if document_letter_head not in letter_heads:
		default_letter_head = frappe.db.get_value("Letter Head", {"disabled": 0, "is_default": 1}, "name")
	return {
		**format_options,
		"default_format": default_format if default_format in formats else "Standard",
		"letter_heads": letter_heads,
		"default_letter_head": resolve_default_letter_head(letter_heads, document_letter_head, default_letter_head),
	}
