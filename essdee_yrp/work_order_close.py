"""Essdee entry point for the base YRP Work Order close lifecycle."""

import frappe
from frappe.utils import flt


@frappe.whitelist()
def close_work_order(
	work_order,
	close_reason=None,
	close_other_reason=None,
	close_remarks=None,
):
	"""Run YRP's Open → Close Request → Close flow and return UI details.

	Base YRP already owns the generic, reservation-aware stock cleanup. Essdee's
	fabric customization feeds its ``stock_update`` from GRN Deliverables; this
	endpoint keeps Desk and /web on that one close implementation.
	"""
	from yrp.yrp.doctype.work_order.work_order import update_stock

	status = update_stock(
		work_order,
		close_reason=close_reason,
		close_other_reason=close_other_reason,
		close_remarks=close_remarks,
	)
	deducted = 0
	if status == "Close":
		deducted = abs(
			flt(
				frappe.db.sql(
					"""
					SELECT COALESCE(SUM(qty), 0)
					FROM `tabStock Ledger Entry`
					WHERE voucher_type = 'Work Order'
					  AND voucher_no = %s
					  AND is_cancelled = 0
					""",
					work_order,
				)[0][0]
			)
		)
	return {
		"status": status,
		"deducted_qty": flt(deducted, 3),
	}
