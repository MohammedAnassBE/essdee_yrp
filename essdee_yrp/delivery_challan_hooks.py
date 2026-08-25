"""Essdee-specific Delivery Challan defaults from the selected Work Order."""

import frappe


def onload(doc, method=None):
	"""Render a cutting DC as one panel/colour row with Size columns."""
	del method
	if not doc.get("cut_panel_movement"):
		return

	from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes
	from yrp.stock.save_stock_items import group_items_for_ui

	doc.set_onload(
		"item_details",
		group_items_for_ui(
			normalize_item_matrix_row_indexes(doc.get("items") or []),
			"Delivery Challan",
		),
	)


WORK_ORDER_FETCH_FIELDS = (
	"is_rework",
	"lot",
	"includes_packing",
)


def before_validate(doc, method=None):
	"""Keep Essdee's read-only Work Order context authoritative on the DC."""
	from essdee_yrp.cutting.movement import validate_transaction_link

	validate_transaction_link(doc)
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
	# ``is_internal_unit`` deliberately is not copied from Work Order.  The WO
	# flag says only that its supplier is a company location, while a DC must
	# compare both endpoints (including the same-location no-transit case).  Base
	# Delivery Challan computes that transaction-specific value authoritatively.
