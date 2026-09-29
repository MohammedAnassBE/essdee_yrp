"""OCR closure and P&L evidence workflow for Essdee Finishing Plans."""

import frappe
from frappe import _
from frappe.utils import add_days, today

from essdee_yrp.production_order_workflow import (
	close_production_order_if_all_lots_audited,
)


@frappe.whitelist()
def get_p_and_l_documents(doc_name):
	plan = frappe.get_doc('SD YRP Finishing Plan', doc_name)
	plan.check_permission("read")
	_require_p_and_l_role()
	return frappe.get_all(
		'SD YRP P and L Document',
		filters={"against": 'SD YRP Finishing Plan', "against_id": doc_name},
		fields=["name", "file", "comments", "modified", "owner"],
		order_by="creation desc",
	)


@frappe.whitelist()
def add_p_and_l_document(doc_name, file_url, comments=None):
	plan = frappe.get_doc('SD YRP Finishing Plan', doc_name)
	plan.check_permission("write")
	_require_p_and_l_role()
	if plan.fp_status != "OCR Completed":
		frappe.throw(_("P&L documents can be added only after OCR is completed."))
	if not file_url:
		frappe.throw(_("File is required."))

	document = frappe.new_doc('SD YRP P and L Document')
	document.update(
		{
			"against": 'SD YRP Finishing Plan',
			"against_id": plan.name,
			"file": file_url,
			"comments": comments,
		}
	)
	# P and L Document is intentionally System-Manager-only as a standalone
	# DocType. The configured merch role reaches it only through this guarded
	# Finishing Plan workflow.
	document.insert(ignore_permissions=True)
	return document.name


@frappe.whitelist()
def delete_p_and_l_document(name):
	document = frappe.get_doc('SD YRP P and L Document', name)
	if document.against != 'SD YRP Finishing Plan' or not document.against_id:
		frappe.throw(_("This is not a Finishing Plan P&L document."))
	plan = frappe.get_doc('SD YRP Finishing Plan', document.against_id)
	plan.check_permission("write")
	_require_p_and_l_role()
	frappe.delete_doc('SD YRP P and L Document', name, ignore_permissions=True)
	return True


def get_accounts_user_role():
	return (
		frappe.db.get_single_value('SD YRP MRP Settings', "accounts_user_role") or ""
	).strip()


def require_accounts_user_role():
	accounts_role = get_accounts_user_role()
	if not accounts_role:
		frappe.throw(_("Configure Accounts User Role in MRP Settings."))
	if accounts_role not in frappe.get_roles():
		frappe.throw(
			_("Only users with the {0} role can complete the audit.").format(
				accounts_role
			)
		)


def close_linked_production_order_if_all_lots_audited(lot):
	production_order = frappe.db.get_value(
		'SD YRP Lot', lot, "production_order"
	)
	if not production_order:
		return False
	return close_production_order_if_all_lots_audited(production_order)


def auto_complete_ocr_after_30_days():
	"""Complete OCR after an audited plan has remained open for over 30 days."""
	cutoff_date = add_days(today(), -30)
	finishing_plans = frappe.get_all(
		'SD YRP Finishing Plan',
		filters={
			"fp_status": "Audit Completed",
			"audit_completed_date": ("<", cutoff_date),
		},
		pluck="name",
	)
	for finishing_plan in finishing_plans:
		frappe.db.set_value(
			'SD YRP Finishing Plan',
			finishing_plan,
			"fp_status",
			"OCR Completed",
		)
	return len(finishing_plans)


@frappe.whitelist()
def request_audit(doc_name):
	plan = frappe.get_doc('SD YRP Finishing Plan', doc_name, for_update=True)
	plan.check_permission("write")
	if plan.fp_status not in ("Dispatched", "Fully Dispatched"):
		frappe.throw(
			_(
				"Audit can be requested only for a Dispatched or Fully Dispatched "
				"Finishing Plan (current: {0})."
			).format(plan.fp_status)
		)
	plan.fp_status = "Ready for Audit"
	plan.audit_requested_date = today()
	plan.audit_completed_date = None
	plan.save(ignore_permissions=True)
	return {
		"fp_status": plan.fp_status,
		"audit_requested_date": plan.audit_requested_date,
	}


@frappe.whitelist()
def complete_audit(doc_name):
	require_accounts_user_role()
	plan = frappe.get_doc('SD YRP Finishing Plan', doc_name, for_update=True)
	if plan.fp_status != "Ready for Audit":
		frappe.throw(
			_("Finishing Plan is not Ready for Audit (current: {0}).").format(
				plan.fp_status
			)
		)
	plan.fp_status = "Audit Completed"
	plan.audit_completed_date = today()
	plan.save(ignore_permissions=True)
	close_linked_production_order_if_all_lots_audited(plan.lot)
	return {
		"fp_status": plan.fp_status,
		"audit_completed_date": plan.audit_completed_date,
	}


@frappe.whitelist()
def complete_ocr(doc_name):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only System Manager can complete OCR."))
	plan = frappe.get_doc('SD YRP Finishing Plan', doc_name, for_update=True)
	if plan.fp_status != "Audit Completed":
		frappe.throw(
			_(
				"OCR can be completed only after the audit is completed "
				"(current: {0})."
			).format(plan.fp_status)
		)
	plan.fp_status = "OCR Completed"
	plan.save(ignore_permissions=True)
	close_linked_production_order_if_all_lots_audited(plan.lot)
	return {"fp_status": plan.fp_status}


@frappe.whitelist()
def approve_ocr_request(doc_name):
	"""Compatibility alias for clients using the previous approval endpoint."""
	return complete_ocr(doc_name)


def _require_p_and_l_role():
	roles = set(frappe.get_roles())
	if "System Manager" in roles:
		return
	merch_role = frappe.db.get_single_value('SD YRP MRP Settings', "merch_user_role")
	if not merch_role or merch_role not in roles:
		frappe.throw(_("You are not permitted to manage Finishing Plan P&L documents."))
