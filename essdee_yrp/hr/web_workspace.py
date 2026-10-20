from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import cint
from yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking import (
	check_for_can_show_receive_btn,
	get_role_permissions,
)

from essdee_yrp.overrides.bill_tracking import (
	CANCEL_APPROVED_STATUS,
	CANCEL_PENDING_STATUS,
	CANCEL_REQUESTABLE_STATUSES,
)
from essdee_yrp.print_registry import get_document_print_formats
from essdee_yrp.sewing.web_workspace import get_capabilities as get_sewing_capabilities
from essdee_yrp.web_common import action, assert_expected_modified, parse_mapping, permission_flags, value

DOCTYPE = "YRP Bill Tracking"
RECEIVED_VIA_DOCTYPE = "YRP Bill Tracking Received Via"
DELIVERY_PERSON_DOCTYPE = "YRP Vendor Bill Delivery Person"
DETAIL_FIELDS = (
	"bill_date",
	"gstin",
	"pan",
	"received_date",
	"received_via",
	"receive_comment",
	"delivery_person",
	"delivery_mob_no",
	"assigned_to",
	"cancel_reason",
	"purchase_invoice",
	"erp_purchase_invoice",
)
EDITOR_FIELDS = (
	"supplier",
	"bill_no",
	"bill_date",
	"invoice_value",
	"received_date",
	"received_via",
	"receive_comment",
	"delivery_mob_no",
)
HISTORY_FIELDS = ("action", "assigned_to", "assigned_by", "assigned_on", "received", "remarks")
RECORD_FIELDS = (
	"doctype",
	"name",
	"docstatus",
	"form_status",
	"modified",
	"supplier",
	"bill_no",
	"invoice_value",
	"purchase_invoice",
	"erp_purchase_invoice",
	"assigned_to",
)
PERMISSION_TYPES = ("read", "write", "create", "submit", "cancel", "delete", "print")
ACTION_LABELS = {
	"assign": _("Assign"),
	"bill_received": _("Bill Received"),
	"request_cancel": _("Request for Cancel"),
	"approve_cancel": _("Approve Cancel Request"),
	"cancel": _("Cancel"),
	"create_purchase_invoice": _("Create YRP Purchase Invoice"),
	"show_purchase_invoice": _("Show YRP Purchase Invoice"),
	"show_erp_purchase_invoice": _("Show ERP Purchase Invoice"),
	"edit": _("Edit"),
	"submit": _("Submit"),
	"delete": _("Delete"),
}


def _can_view_attendance():
	return bool(
		get_sewing_capabilities()["sections"].get("attendance", {}).get("can_read")
	)


@frappe.whitelist()
def get_capabilities() -> dict:
	reports = {}
	if _can_view_attendance():
		reports["attendance"] = {"label": _("Attendance"), "can_read": True}
	return {
		"sections": {
			"bill_tracking": {
				"label": _("Bill Tracking"),
				"can_read": bool(frappe.has_permission("YRP Bill Tracking", ptype="read")),
				"can_create": bool(frappe.has_permission("YRP Bill Tracking", ptype="create")),
			},
			"reports": {"label": _("Reports"), "can_read": bool(reports)},
		},
		"reports": reports,
	}


def _readable_fieldnames(source):
	if isinstance(source, Mapping):
		return source.keys()
	return getattr(source, "permitted_fieldnames", vars(source).keys())


def _serialize_present_fields(source, fieldnames) -> dict:
	readable_fields = _readable_fieldnames(source)
	return {
		fieldname: value(source, fieldname)
		for fieldname in fieldnames
		if fieldname in readable_fields
	}


def _has_purchase_invoice(doc) -> bool:
	return bool(doc.get("purchase_invoice") or doc.get("erp_purchase_invoice"))


def _has_unreceived_last_assignment(doc) -> bool:
	assigned_to = doc.get("assigned_to")
	last_assignment = None
	for row in doc.get("bill_tracking_history") or []:
		if value(row, "assigned_to") == assigned_to:
			last_assignment = row
	return bool(assigned_to and last_assignment and not cint(value(last_assignment, "received")))


def _can_create_purchase_invoice(doc, role_permissions) -> bool:
	is_cancel_pending = doc.get("form_status") in {CANCEL_PENDING_STATUS, CANCEL_APPROVED_STATUS}
	return bool(
		cint(doc.docstatus) == 1
		and not _has_purchase_invoice(doc)
		and not is_cancel_pending
		and role_permissions.get("can_create_invoice")
		and frappe.has_permission("YRP Purchase Invoice", ptype="create")
	)


def bill_tracking_actions(doc, permissions, role_permissions, can_acknowledge) -> dict:
	docstatus = cint(doc.docstatus)
	status = doc.get("form_status")
	has_invoice = _has_purchase_invoice(doc)
	is_cancel_pending = status in {CANCEL_PENDING_STATUS, CANCEL_APPROVED_STATUS}
	conditions = {
		"assign": docstatus == 1 and status not in {"Closed", "Cancelled"} and not is_cancel_pending
		and permissions.get("can_write"),
		"bill_received": docstatus == 1 and status != "Closed" and not is_cancel_pending
		and _has_unreceived_last_assignment(doc) and can_acknowledge,
		"request_cancel": docstatus == 1 and not has_invoice
		and status in CANCEL_REQUESTABLE_STATUSES and role_permissions.get("can_request_cancel"),
		"approve_cancel": status == CANCEL_PENDING_STATUS and not has_invoice
		and role_permissions.get("can_approve_cancel"),
		"cancel": status == CANCEL_APPROVED_STATUS and not has_invoice
		and role_permissions.get("can_request_cancel"),
		"create_purchase_invoice": _can_create_purchase_invoice(doc, role_permissions),
		"show_purchase_invoice": bool(doc.get("purchase_invoice")),
		"show_erp_purchase_invoice": bool(doc.get("erp_purchase_invoice")),
		"edit": docstatus == 0 and permissions.get("can_write"),
		"submit": docstatus == 0 and permissions.get("can_submit"),
		"delete": docstatus == 0 and permissions.get("can_delete"),
	}
	reason = _("This action is not available for the current document state or your permissions.")
	return {
		key: action(allowed, ACTION_LABELS[key], reason)
		for key, allowed in conditions.items()
	}


def _record(doc) -> dict:
	record = _serialize_present_fields(doc, RECORD_FIELDS)
	if "docstatus" in record:
		record["docstatus"] = cint(record["docstatus"])
	return record


def _field_schema(doc, fieldname: str) -> dict:
	field = doc.meta.get_field(fieldname)
	return {
		"label": field.label if field and field.label else fieldname.replace("_", " ").title(),
		"fieldtype": field.fieldtype if field else "Data",
		"options": field.options if field else None,
		"reqd": bool(field.reqd) if field else False,
	}


def _detail_field(doc, fieldname: str) -> dict:
	return {"fieldname": fieldname, **_field_schema(doc, fieldname), "value": doc.get(fieldname)}


def serialize_details(doc) -> list[dict]:
	readable_fields = _readable_fieldnames(doc)
	return [
		_detail_field(doc, fieldname)
		for fieldname in DETAIL_FIELDS
		if fieldname in readable_fields and doc.get(fieldname) not in (None, "")
	]


def serialize_history(doc) -> list[dict]:
	return [
		_serialize_present_fields(row, HISTORY_FIELDS)
		for row in doc.get("bill_tracking_history") or []
	]


def _can_acknowledge(doc) -> bool:
	status = doc.get("form_status")
	is_available = cint(doc.docstatus) == 1 and status != "Closed"
	is_available = is_available and status not in {CANCEL_PENDING_STATUS, CANCEL_APPROVED_STATUS}
	if not is_available or not _has_unreceived_last_assignment(doc):
		return False
	return bool(check_for_can_show_receive_btn(doc.name))


@frappe.whitelist()
def get_bill_tracking_workspace(name: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	permissions = permission_flags(DOCTYPE, PERMISSION_TYPES, doc)
	role_permissions = get_role_permissions()
	capabilities = bill_tracking_actions(
		doc, permissions, role_permissions, _can_acknowledge(doc)
	)
	can_open_desk = "System Manager" in frappe.get_roles()
	doc.apply_fieldlevel_read_permissions()
	return {
		"record": _record(doc),
		"print_formats": get_document_print_formats(doc),
		"details": serialize_details(doc),
		"history": serialize_history(doc),
		"permissions": permissions,
		"capabilities": capabilities,
		"can_open_desk": can_open_desk,
	}


def _get_draft_for_save(name, expected_modified):
	if not name:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		return frappe.new_doc(DOCTYPE), True
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	doc.check_permission("write")
	if cint(doc.docstatus) != 0:
		frappe.throw(_("Only a draft Bill Tracking record can be edited."))
	assert_expected_modified(doc, expected_modified)
	return doc, False


@frappe.whitelist()
def get_bill_tracking_editor(name: str | None = None) -> dict:
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		doc.check_permission("write")
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a draft Bill Tracking record can be edited."))
	else:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		doc = frappe.new_doc(DOCTYPE)
	can_create_delivery_person = bool(
		frappe.has_permission(DELIVERY_PERSON_DOCTYPE, ptype="create")
	)
	can_submit = bool(frappe.has_permission(DOCTYPE, ptype="submit", doc=doc))
	doc.apply_fieldlevel_read_permissions()
	return {
		"values": _serialize_present_fields(doc, EDITOR_FIELDS),
		"received_via_options": frappe.get_all(
			RECEIVED_VIA_DOCTYPE, filters={"disabled": 0}, pluck="name", order_by="name asc"
		),
		"schema": {fieldname: _field_schema(doc, fieldname) for fieldname in EDITOR_FIELDS},
		"modified": doc.get("modified") if name else None,
		"can_create_delivery_person": can_create_delivery_person,
		"can_submit": can_submit,
	}


@frappe.whitelist()
def save_bill_tracking(values, name=None, submit=False, expected_modified=None) -> dict:
	values = parse_mapping(values, _("Bill Tracking values"))
	doc, is_new = _get_draft_for_save(name, expected_modified)
	if cint(submit):
		doc.check_permission("submit")
	for fieldname in EDITOR_FIELDS:
		if fieldname in values:
			doc.set(fieldname, values[fieldname])
	if is_new:
		doc.insert()
	else:
		doc.save()
	if cint(submit):
		doc.submit()
	return get_bill_tracking_workspace(doc.name)


def _require_command(doc, command: str) -> None:
	permissions = permission_flags(DOCTYPE, PERMISSION_TYPES, doc)
	actions = bill_tracking_actions(doc, permissions, get_role_permissions(), False)
	if not actions[command]["allowed"]:
		frappe.throw(actions[command]["reason"], frappe.PermissionError)


@frappe.whitelist()
def execute_bill_tracking_command(name, command, expected_modified=None) -> dict:
	if command not in {"submit", "delete"}:
		frappe.throw(_("Unsupported Bill Tracking action: {0}").format(command))
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	assert_expected_modified(doc, expected_modified)
	_require_command(doc, command)
	doc.check_permission(command)
	if command == "submit":
		doc.submit()
		return get_bill_tracking_workspace(doc.name)
	frappe.delete_doc(DOCTYPE, doc.name)
	return {"deleted": True, "record": {"name": doc.name}}
