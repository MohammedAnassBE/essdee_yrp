"""Authoritative Essdee packing-flag propagation across transactions."""

import frappe


def set_grn_includes_packing(doc, method=None):
	if not doc.meta.get_field("includes_packing"):
		return
	doc.includes_packing = 0
	if doc.get("process_name") and frappe.get_meta('YRP Process').get_field("includes_packing"):
		doc.includes_packing = frappe.db.get_value(
			'YRP Process', doc.process_name, "includes_packing"
		) or 0


def set_stock_entry_includes_packing(doc, method=None):
	if not doc.meta.get_field("includes_packing"):
		return
	doc.includes_packing = 0
	source_doctype = doc.get("against")
	source_name = doc.get("against_id")
	if source_doctype not in ('YRP Work Order', 'YRP Delivery Challan', 'YRP Goods Received Note'):
		return
	if not source_name or not frappe.get_meta(source_doctype).get_field("includes_packing"):
		return
	doc.includes_packing = frappe.db.get_value(
		source_doctype, source_name, "includes_packing"
	) or 0
