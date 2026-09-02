"""OCR closure and P&L evidence workflow for Essdee Finishing Plans."""

import frappe
from frappe import _
from frappe.utils import flt

from essdee_yrp.finishing.status import get_unaccountable_quantity


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


@frappe.whitelist()
def approve_ocr_request(doc_name):
	if "System Manager" not in frappe.get_roles():
		frappe.throw(_("Only a System Manager can approve OCR requests."))
	plan = frappe.get_doc('SD YRP Finishing Plan', doc_name)
	plan.check_permission("write")
	if plan.fp_status != "OCR Requested":
		frappe.throw(
			_("Finishing Plan is not in OCR Requested state (current: {0}).").format(
				plan.fp_status
			)
		)
	plan.fp_status = "OCR Completed"
	plan.save()
	return {"fp_status": plan.fp_status}


@frappe.whitelist()
def complete_ocr(doc_name):
	plan = frappe.get_doc('SD YRP Finishing Plan', doc_name)
	plan.check_permission("write")
	if plan.fp_status not in ("Dispatched", "Fully Dispatched"):
		frappe.throw(
			_("OCR can be completed only for a dispatched Finishing Plan.")
		)
	unaccountable = flt(get_unaccountable_quantity(plan), 6)
	plan.fp_status = "OCR Completed" if abs(unaccountable) < 0.000001 else "OCR Requested"
	plan.save()
	return {"fp_status": plan.fp_status, "unaccountable": unaccountable}


def _require_p_and_l_role():
	roles = set(frappe.get_roles())
	if "System Manager" in roles:
		return
	merch_role = frappe.db.get_single_value('SD YRP MRP Settings', "merch_user_role")
	if not merch_role or merch_role not in roles:
		frappe.throw(_("You are not permitted to manage Finishing Plan P&L documents."))
