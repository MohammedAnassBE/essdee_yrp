"""Essdee-specific Delivery Challan defaults from the selected Work Order."""

import frappe


@frappe.whitelist()
def create_return_grn(doc_name, items, received_type=None, cut_panel_movement=None):
	"""Create the base-authorized return draft and optionally bind whole bundles."""
	from yrp.yrp.doctype.yrp_delivery_challan.yrp_delivery_challan import (
		create_return_grn as create_base_return_grn,
	)

	name = create_base_return_grn(doc_name, items, received_type)
	if cut_panel_movement:
		grn = frappe.get_doc('YRP Goods Received Note', name)
		grn.cut_panel_movement = cut_panel_movement
		grn.save()
	return name


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
			'YRP Delivery Challan',
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

	work_order_meta = frappe.get_meta('YRP Work Order')
	fieldnames = [
		fieldname
		for fieldname in WORK_ORDER_FETCH_FIELDS
		if work_order_meta.get_field(fieldname) and doc.meta.get_field(fieldname)
	]
	if not fieldnames:
		return

	values = frappe.db.get_value('YRP Work Order', doc.work_order, fieldnames, as_dict=True)
	if not values:
		return

	for fieldname in fieldnames:
		doc.set(fieldname, values.get(fieldname))
	# ``is_internal_unit`` deliberately is not copied from Work Order.  The WO
	# flag says only that its supplier is a company location, while a DC must
	# compare both endpoints (including the same-location no-transit case).  Base
	# Delivery Challan computes that transaction-specific value authoritatively.


def sync_cutting_plan_received_cloth(doc, method=None):
	"""Reflect a submitted/cancelled DC in every linked Cutting Plan."""
	del method
	if not doc.get("work_order"):
		return
	from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
		rebuild_received_cloth,
	)

	for name in frappe.get_all(
		'SD YRP Cutting Plan',
		filters={"work_order": doc.work_order, "docstatus": 1},
		pluck="name",
	):
		rebuild_received_cloth(frappe.get_doc('SD YRP Cutting Plan', name))
