import frappe

from yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking import YRPBillTracking


CANCEL_REQUEST_ROLE_FIELD = "bill_tracking_cancel_request_role"
CANCEL_APPROVER_ROLE_FIELD = "bill_tracking_cancel_approver_role"
CANCEL_PENDING_STATUS = "Pending Approval"
CANCEL_APPROVED_STATUS = "Cancel Request Approved"
CANCEL_REQUESTABLE_STATUSES = frozenset({"Open", "Assigned", "Reopen", "Amended"})


def _require_role(role_field):
	"""Enforce the YRP Settings role that the Bill Tracking form also reads."""
	role = frappe.db.get_single_value("YRP Settings", role_field)
	if not role:
		frappe.throw(f"Set {role_field.replace('_', ' ').title()} in YRP Settings", frappe.PermissionError)
	if role not in frappe.get_roles():
		frappe.throw(f"Only users with the {role} role can perform this action", frappe.PermissionError)


def _get_locked_bill_tracking(name):
	frappe.db.get_value("YRP Bill Tracking", name, "name", for_update=True)
	return frappe.get_doc("YRP Bill Tracking", name)


def _validate_submitted_without_purchase_invoice(doc):
	if doc.docstatus != 1:
		frappe.throw("YRP Bill Tracking must be submitted")
	if doc.purchase_invoice or doc.erp_purchase_invoice:
		frappe.throw("YRP Bill Tracking with a Purchase Invoice cannot be cancelled")


def _validate_cancel_approved_without_purchase_invoice(doc):
	if doc.form_status != CANCEL_APPROVED_STATUS:
		frappe.throw("Cancellation must be approved before cancelling YRP Bill Tracking")
	if doc.purchase_invoice or doc.erp_purchase_invoice:
		frappe.throw("YRP Bill Tracking with a Purchase Invoice cannot be cancelled")


class EssdeeYRPBillTracking(YRPBillTracking):
	def before_cancel(self):
		_require_role(CANCEL_REQUEST_ROLE_FIELD)
		_validate_cancel_approved_without_purchase_invoice(self)
		super().before_cancel()


@frappe.whitelist()
def request_bill_cancellation(name):
	_require_role(CANCEL_REQUEST_ROLE_FIELD)
	doc = _get_locked_bill_tracking(name)
	_validate_submitted_without_purchase_invoice(doc)
	if doc.form_status not in CANCEL_REQUESTABLE_STATUSES:
		frappe.throw(f"Cannot request cancellation while status is {doc.form_status}")
	doc.set("form_status", CANCEL_PENDING_STATUS)
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def approve_bill_cancellation(name):
	_require_role(CANCEL_APPROVER_ROLE_FIELD)
	doc = _get_locked_bill_tracking(name)
	_validate_submitted_without_purchase_invoice(doc)
	if doc.form_status != CANCEL_PENDING_STATUS:
		frappe.throw(f"Cannot approve cancellation while status is {doc.form_status}")
	doc.set("form_status", CANCEL_APPROVED_STATUS)
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def cancel_vendor_bill(name, cancel_reason):
	_require_role(CANCEL_REQUEST_ROLE_FIELD)
	doc = _get_locked_bill_tracking(name)
	_validate_submitted_without_purchase_invoice(doc)
	_validate_cancel_approved_without_purchase_invoice(doc)
	doc.cancel_reason = cancel_reason
	doc.flags.ignore_permissions = True
	doc.cancel()
