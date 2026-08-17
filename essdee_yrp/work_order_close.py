"""Essdee entry point for the base YRP Work Order close lifecycle."""

import frappe
from frappe import _
from frappe.utils import flt


SD_CLOSE_REASONS = (
	"NA",
	"Cutting Shortage",
	"Printing Shortage",
	"Sewing Shortage",
	"Sewing Missing",
	"Others",
)


@frappe.whitelist()
def close_work_order(
	work_order,
	sd_close_reason=None,
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

	# ``close_reason`` is retained as an input alias for the base Desk dialog,
	# whose generic fieldname must remain unchanged. The selected Essdee reason
	# is stored only in the Essdee-owned ``sd_close_reason`` Custom Field.
	selected_reason = (sd_close_reason or close_reason or "").strip()
	if selected_reason not in SD_CLOSE_REASONS:
		frappe.throw(_("Select a valid SD Close Reason."))
	other_reason = (close_other_reason or "").strip()
	if selected_reason == "Others" and not other_reason:
		frappe.throw(_("Enter the other close reason."))
	if selected_reason != "Others":
		other_reason = ""

	was_closed = frappe.db.get_value("Work Order", work_order, "open_status") == "Close"

	status = update_stock(
		work_order,
		close_reason=None,
		close_other_reason=None,
		close_remarks=close_remarks,
	)
	if not was_closed:
		frappe.db.set_value(
			"Work Order",
			work_order,
			{
				"sd_close_reason": selected_reason,
				"close_other_reason": other_reason,
			},
			update_modified=False,
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
