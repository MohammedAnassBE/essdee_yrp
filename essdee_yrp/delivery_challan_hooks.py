"""Essdee-specific Delivery Challan defaults from the selected Work Order."""

import frappe


def before_validate(doc, method=None):
	"""Keep the Work Order's packing rule authoritative on the DC."""
	if not doc.get("work_order") or not doc.meta.get_field("includes_packing"):
		return
	if not frappe.get_meta("Work Order").get_field("includes_packing"):
		return

	doc.includes_packing = frappe.db.get_value(
		"Work Order", doc.work_order, "includes_packing"
	) or 0
