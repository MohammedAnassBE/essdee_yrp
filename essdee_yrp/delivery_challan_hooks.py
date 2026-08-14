"""Essdee-specific Delivery Challan defaults from the selected Work Order."""

import frappe


WORK_ORDER_FETCH_FIELDS = (
	"is_internal_unit",
	"is_rework",
	"lot",
	"includes_packing",
)


def before_validate(doc, method=None):
	"""Keep Essdee's read-only Work Order context authoritative on the DC."""
	if not doc.work_order:
		return

	work_order_meta = frappe.get_meta("Work Order")
	fieldnames = [
		fieldname
		for fieldname in WORK_ORDER_FETCH_FIELDS
		if work_order_meta.get_field(fieldname) and doc.meta.get_field(fieldname)
	]
	if not fieldnames:
		return

	values = frappe.db.get_value("Work Order", doc.work_order, fieldnames, as_dict=True)
	if not values:
		return

	for fieldname in fieldnames:
		doc.set(fieldname, values.get(fieldname))
