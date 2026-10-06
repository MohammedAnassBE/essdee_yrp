from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.model.workflow import apply_workflow
from frappe.utils import now_datetime


class TelegramApprovalPermissionError(frappe.PermissionError):
	pass


class TelegramApprovalStateError(frappe.ValidationError):
	pass


def _current_user():
	return frappe.session.user


def execute_action(request_doc, route, frappe_user, action_key):
	doc = frappe.get_doc(request_doc.reference_doctype, request_doc.reference_name)
	current_value = str(doc.get(request_doc.state_field) or "")
	if current_value != str(request_doc.source_value or ""):
		raise TelegramApprovalStateError(
			_("This document is no longer in {0}. Current value: {1}.").format(
				request_doc.source_value, current_value or _("empty")
			)
		)

	action_name = _get_action_name(route, action_key)
	original_user = frappe.session.user
	previous_flag = frappe.flags.get("in_telegram_approval_action")
	frappe.set_user(frappe_user)
	frappe.flags.in_telegram_approval_action = True
	try:
		if route.process_type == "Workflow":
			updated_doc = apply_workflow(doc.as_dict(), action_name)
		else:
			updated_doc = _apply_field_state_action(doc, route, action_key, action_name)
	finally:
		frappe.flags.in_telegram_approval_action = previous_flag
		frappe.set_user(original_user)
	return action_name, updated_doc


def _get_action_name(route, action_key):
	fieldname = "approve_action" if action_key == "a" else "reject_action"
	action_name = route.get(fieldname)
	if not action_name:
		raise TelegramApprovalStateError(_("This action is not configured."))
	return action_name


def _apply_field_state_action(doc, route, action_key, action_name):
	doc.check_permission("write")
	_validate_action_roles(route, action_key, action_name)
	target_field = route.get("target_field")
	if not target_field or not doc.meta.has_field(target_field):
		raise TelegramApprovalStateError(
			_("Configured target field {0} does not exist on {1}.").format(
				target_field or _("empty"), doc.doctype
			)
		)
	target_value = route.get("approve_value") if action_key == "a" else route.get("reject_value")
	if target_value in (None, ""):
		raise TelegramApprovalStateError(
			_("No target value is configured for action {0}.").format(action_name)
		)
	handler = FIELD_STATE_ACTION_HANDLERS.get(doc.doctype)
	if handler:
		return handler(doc, route, action_key, action_name, target_field, target_value)
	doc.set(target_field, target_value)
	doc.save()
	doc.add_comment(
		"Comment", _("Telegram action {0} performed by {1}.").format(action_name, frappe.session.user)
	)
	return doc


def _validate_action_roles(route, action_key, action_name):
	required_roles = _parse_roles(
		route.get("approve_roles") if action_key == "a" else route.get("reject_roles")
	)
	if required_roles and not set(frappe.get_roles()).intersection(required_roles):
		raise TelegramApprovalPermissionError(
			_("You are not authorized to perform {0} on this document.").format(action_name)
		)


def _apply_purchase_order_action(doc, route, action_key, action_name, target_field, target_value):
	expected = {"a": ("Approve PO", "Ordered"), "r": ("Reject PO", "Draft")}.get(action_key)
	if target_field != "status" or not expected or (action_name, target_value) != expected:
		raise TelegramApprovalStateError(
			_("Invalid Purchase Order Telegram approval action configuration.")
		)
	from essdee_yrp.purchase_order_approval import approve_purchase_order, reject_purchase_order

	if action_key == "a":
		approve_purchase_order(doc.name)
	else:
		reject_purchase_order(doc.name)
	updated_doc = frappe.get_doc("Purchase Order", doc.name)
	updated_doc.add_comment(
		"Comment", _("Telegram action {0} performed by {1}.").format(action_name, _current_user())
	)
	return updated_doc


def _apply_purchase_invoice_action(doc, route, action_key, action_name, target_field, target_value):
	if target_field != "status":
		raise TelegramApprovalStateError(
			_("Purchase Invoice Telegram approvals must update the status field.")
		)
	source_status = str(doc.status or "")
	allowed = {"Approval Initiated": "Approval Pending", "Approval Pending": "Approved"}
	if action_key == "a" and allowed.get(source_status) != target_value:
		raise TelegramApprovalStateError(
			_("Invalid Purchase Invoice approval transition: {0} to {1}.").format(
				source_status, target_value
			)
		)
	if action_key == "a" and target_value == "Approval Pending":
		doc.senior_merch_approved_by = frappe.session.user
	elif action_key == "a" and target_value == "Approved":
		_validate_purchase_invoice_work_orders(doc)
		doc.approved_by = frappe.session.user
		if not doc.senior_merch_approved_by:
			doc.senior_merch_approved_by = frappe.session.user
	elif action_key == "r" and target_value == "Draft":
		doc.approved_by = None
		doc.senior_merch_approved_by = None
	doc.set(target_field, target_value)
	doc.append(
		"purchase_invoice_wo_approval_details",
		{
			"user": frappe.session.user,
			"approved_time": now_datetime(),
			"comments": _("{0} through Telegram").format(action_name),
		},
	)
	doc.save()
	doc.add_comment(
		"Comment", _("Telegram action {0} performed by {1}.").format(action_name, frappe.session.user)
	)
	return doc


def _validate_purchase_invoice_work_orders(doc):
	if doc.against != "YRP Work Order":
		return
	if frappe.db.get_single_value("YRP Settings", "override_pi_approve"):
		return
	from yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice import check_all_wo_closed

	result = check_all_wo_closed(doc.name)
	if result["all_closed"]:
		return
	work_orders = result["open_work_orders"] + result["close_request_wos"]
	raise TelegramApprovalStateError(
		_("Cannot approve because these Work Orders are not closed: {0}.").format(
			", ".join(work_orders)
		)
	)


def _parse_roles(value):
	if not value:
		return set()
	return {role.strip() for role in re.split(r"[,\n]", value) if role.strip()}


FIELD_STATE_ACTION_HANDLERS = {
	"Purchase Order": _apply_purchase_order_action,
	"YRP Purchase Invoice": _apply_purchase_invoice_action,
}
