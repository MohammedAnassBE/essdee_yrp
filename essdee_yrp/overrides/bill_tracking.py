import frappe
from frappe import _
from frappe.utils import escape_html
from yrp.yrp.doctype.yrp_bill_tracking import yrp_bill_tracking as base_bill_tracking

CANCEL_REQUEST_ROLE_FIELD = "bill_tracking_cancel_request_role"
CANCEL_APPROVER_ROLE_FIELD = "bill_tracking_cancel_approver_role"
CANCEL_PENDING_STATUS = "Pending Approval"
CANCEL_APPROVED_STATUS = "Cancel Request Approved"
CANCEL_REQUESTABLE_STATUSES = frozenset({"Open", "Assigned", "Reopen", "Amended"})
BULK_ASSIGN_LIMIT = 200


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


class EssdeeYRPBillTracking(base_bill_tracking.YRPBillTracking):
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


@frappe.whitelist()
def assign_vendor_bill(name, assigned_to, remarks=None):
	"""Assign a bill only when the caller may write it."""
	frappe.get_doc("YRP Bill Tracking", name).check_permission("write")
	return base_bill_tracking.assign_vendor_bill(name, assigned_to, remarks=remarks)


def get_bulk_assignment_failure_reason(exception):
	reason = str(exception).strip() or str(getattr(frappe.flags, "error_message", "") or "").strip()
	if reason:
		return reason
	if isinstance(exception, frappe.PermissionError):
		return _("No permission to assign this bill")
	return exception.__class__.__name__


@frappe.whitelist()
def bulk_assign_bills(assign_to, selected_docs, remarks=None):
	"""Assign eligible bills and report validation or permission failures."""
	selected_docs = frappe.parse_json(selected_docs) if isinstance(selected_docs, str) else selected_docs
	if len(selected_docs) > BULK_ASSIGN_LIMIT:
		frappe.throw(f"Select at most {BULK_ASSIGN_LIMIT} bills", frappe.ValidationError)

	result = {"assigned": [], "skipped": []}
	for index, entry in enumerate(selected_docs):
		name = entry["name"] if isinstance(entry, dict) else entry
		savepoint = f"bulk_assign_bill_{index}"
		previous_error_message = getattr(frappe.flags, "error_message", None)
		previous_message_log = list(getattr(frappe.local, "message_log", []) or [])
		frappe.flags.error_message = None
		frappe.db.savepoint(savepoint)
		try:
			assign_vendor_bill(name, assign_to, remarks)
		except (frappe.ValidationError, frappe.PermissionError) as exception:
			reason = get_bulk_assignment_failure_reason(exception)
			frappe.db.rollback(save_point=savepoint)
			frappe.local.message_log = previous_message_log
			result["skipped"].append({"name": name, "reason": reason})
		else:
			result["assigned"].append(name)
		finally:
			frappe.flags.error_message = previous_error_message
	if result["skipped"]:
		items = "".join(
			f"<li><strong>{escape_html(str(row['name']))}</strong>: "
			f"{escape_html(str(row['reason']))}</li>"
			for row in result["skipped"]
		)
		frappe.msgprint(
			f"<ul>{items}</ul>",
			title=_("Some bills were not assigned"),
			indicator="orange",
		)
	return result


@frappe.whitelist()
def make_bill_received_acknowledgement(doc_name):
	"""Acknowledge receipt only when the caller may read the bill."""
	frappe.get_doc("YRP Bill Tracking", doc_name).check_permission("read")
	return base_bill_tracking.make_bill_received_acknowledgement(doc_name)
