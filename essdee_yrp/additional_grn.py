"""Additional receipts use WO identities without the ordinary pending cap."""

import frappe
from frappe import _
from frappe.utils import flt

from yrp.stock.save_stock_items import group_items_for_ui
from yrp.stock.dimensions import apply_dimension_defaults
from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import (
	_apply_dimension_values_to_rows,
	_get_production_group_dimensions,
	_find_matching_receivable,
	_get_received_type_options,
	get_work_order_defaults,
)


@frappe.whitelist()
def get_defaults(work_order):
	defaults = get_work_order_defaults(work_order)
	wo = frappe.get_doc("YRP Work Order", work_order)
	types, default_type = _get_received_type_options(None)
	rows = []
	for source in wo.receivables:
		for received_type in [default_type or types[0]]:
			rows.append(frappe._dict(
				item_variant=source.item_variant, quantity=0, uom=source.uom,
				pending_quantity=source.pending_quantity, max_receivable_quantity=-1,
				ref_doctype=source.doctype, ref_docname=source.name,
				table_index=source.table_index, row_index=f"{source.row_index}::{received_type}",
				set_combination=source.set_combination, rate=source.cost,
				received_type=received_type, lot=wo.get("lot"),
			))
	_apply_dimension_values_to_rows(rows, _get_production_group_dimensions(wo))
	apply_dimension_defaults(rows)
	from essdee_yrp.overrides.goods_received_note import normalize_cutting_grn_row_indexes

	rows = normalize_cutting_grn_row_indexes(rows)
	defaults.update(items=rows, item_details=group_items_for_ui(rows, "YRP Goods Received Note"),
		correction_items=[], correction_item_details=[])
	return defaults


def validate_receivables(grn):
	if grn.against != "YRP Work Order" or grn.get("is_return") or grn.get("is_rework"):
		frappe.throw(_("Additional GRN requires a regular Work Order receipt."))
	if grn.get("correction_items"):
		frappe.throw(_("Additional GRN cannot contain correction items."))
	wo = frappe.get_doc("YRP Work Order", grn.against_id)
	for row in grn.items:
		target = _find_matching_receivable(wo.receivables, row)
		if not target:
			frappe.throw(_("Row {0}: no matching Work Order Receivable found for {1}.").format(row.idx, row.item_variant))
		if flt(row.quantity) <= 0:
			frappe.throw(_("Quantity must be greater than zero."))
		row.ref_doctype = target.doctype
		row.ref_docname = target.name
		row.pending_quantity = target.pending_quantity
		row.max_receivable_quantity = -1


def validate_submit_role():
	role = frappe.db.get_single_value("SD YRP MRP Settings", "additional_grn_submit_role")
	if not role:
		frappe.throw(_("Set the role for additional GRN submit in SD YRP MRP Settings."))
	if role not in frappe.get_roles():
		frappe.throw(_("Only {0} can submit an Additional GRN.").format(role), frappe.PermissionError)
