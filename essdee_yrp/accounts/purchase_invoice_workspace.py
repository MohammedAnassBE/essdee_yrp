from collections.abc import Mapping

import frappe
from frappe import _
from frappe.model.base_document import BaseDocument
from frappe.utils import cint
from yrp.yrp.doctype.yrp_work_order.yrp_work_order import get_close_permission

from essdee_yrp.erp_purchase_invoice import is_erp_purchase_invoice_available
from essdee_yrp.print_registry import get_document_print_formats
from essdee_yrp.purchase_invoice import build_verification_details
from essdee_yrp.web_common import action, permission_flags, value

DOCTYPE = "YRP Purchase Invoice"
PERMISSION_TYPES = ("read", "write", "create", "submit", "cancel", "delete", "amend", "print")
NUMERIC_FIELD_TYPES = frozenset({"Currency", "Float", "Int", "Percent"})
DETAIL_FIELDS = (
	"against",
	"posting_date",
	"due_date",
	"billing_supplier",
	"bill_date",
	"bill_tracking",
	"eligibility_for_itc",
	"debit_type",
	"debit_no",
	"debit_value",
	"erp_inv_name",
	"final_amount",
	"remarks",
)
TOTAL_FIELDS = (
	("total", _("Total")),
	("total_tax", _("Total Tax")),
	("grand_total", _("Grand Total")),
	("total_quantity", _("Quantity")),
)
ITEM_FIELDS = (
	"group_key",
	"item",
	"lot",
	"qty",
	"uom",
	"source_rate",
	"rate",
	"tax",
	"amount",
	"expense_head",
)
ACTION_LABELS = {
	"edit": _("Edit"),
	"submit": _("Submit"),
	"approve": _("Approve Invoice"),
	"fetch_expense_head": _("Fetch Expense Head"),
	"show_erp_bill": _("Show ERP Bill"),
	"submit_erp_bill": _("Submit ERP Bill"),
	"cancel": _("Cancel"),
	"amend": _("Amend"),
	"delete": _("Delete"),
}


def _invoice_link_name(doc, fieldname):
	masked = getattr(getattr(doc, "flags", None), "masked_fieldnames", ()) or ()
	return "" if fieldname in masked else doc.get(fieldname)


def _record(doc) -> dict:
	status = doc.get("status") or {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}.get(
		cint(doc.docstatus), _("Draft")
	)
	return {
		"doctype": doc.doctype,
		"name": doc.name,
		"docstatus": cint(doc.docstatus),
		"status": status,
		"modified": doc.get("modified"),
		"supplier": doc.get("supplier"),
		"supplier_link_name": _invoice_link_name(doc, "supplier"),
		"bill_no": doc.get("bill_no"),
		"against": doc.get("against"),
		"grand_total": doc.get("grand_total"),
		"bill_tracking": doc.get("bill_tracking"),
	}


def apply_purchase_invoice_response_permissions(doc) -> bool:
	duplicate_billing_supplier = doc.get("billing_supplier") == doc.get("supplier")
	doc.apply_fieldlevel_read_permissions()
	return duplicate_billing_supplier


def _supplier_display_name(doc, fieldname):
	name = _invoice_link_name(doc, fieldname)
	if not name:
		return doc.get(fieldname)
	return frappe.db.get_value("Supplier", name, "supplier_name") or name


def _detail_field(doc, fieldname: str) -> dict:
	field = doc.meta.get_field(fieldname)
	return {
		"fieldname": fieldname,
		"label": field.label if field and field.label else fieldname.replace("_", " ").title(),
		"fieldtype": field.fieldtype if field else "Data",
		"value": _supplier_display_name(doc, fieldname)
		if fieldname == "billing_supplier"
		else doc.get(fieldname),
		"options": field.options if field else None,
		**({"link_name": _invoice_link_name(doc, fieldname)} if field and field.fieldtype == "Link" else {}),
	}


def serialize_purchase_invoice_details(doc, duplicate_billing_supplier: bool = False) -> list[dict]:
	details = []
	for fieldname in DETAIL_FIELDS:
		if fieldname == "billing_supplier" and (
			duplicate_billing_supplier or doc.get("billing_supplier") == doc.get("supplier")
		):
			continue
		detail = _detail_field(doc, fieldname)
		value = detail["value"]
		if value in (None, ""):
			continue
		if detail["fieldtype"] in NUMERIC_FIELD_TYPES and value == 0:
			continue
		details.append(detail)
	return details


def serialize_grouped_items(doc) -> list[dict]:
	rows = doc.get("essdee_items") or doc.get("items") or []
	return [
		{fieldname: value(row, fieldname) for fieldname in ITEM_FIELDS}
		for row in rows
	]


def serialize_grns(doc) -> list[dict]:
	names = [row.get("grn") for row in doc.get("grn") or [] if row.get("grn")]
	if not names:
		return []
	rows = frappe.get_list(
		"YRP Goods Received Note",
		filters={"name": ["in", names]},
		fields=[
			"name as grn",
			"posting_date",
			"against",
			"against_id",
			"supplier_document_no",
			"total_received_quantity",
			"total as grand_total",
		],
		limit_page_length=0,
	)
	rows_by_name = {row.grn: dict(row) for row in rows}
	return [rows_by_name[name] for name in names if name in rows_by_name]


def _work_order_names(doc) -> list[str]:
	return list(
		dict.fromkeys(
			row.get("work_order")
			for row in doc.get("pi_work_order_billed_details") or []
			if row.get("work_order")
		)
	)


def serialize_work_orders(doc, close_permission: Mapping | None = None) -> list[dict]:
	names = _work_order_names(doc)
	if not names:
		return []
	rows = frappe.get_list(
		"YRP Work Order",
		filters={"name": ["in", names]},
		fields=["name", "open_status", "modified", "expected_delivery_date"],
		limit_page_length=0,
	)
	rows_by_name = {row.name: row for row in rows}
	result = []
	for name in names:
		if row := rows_by_name.get(name):
			result.append({
				"name": row.name,
				"open_status": row.open_status,
				"modified": row.modified,
				"expected_delivery_date": row.expected_delivery_date,
				"close_mode": work_order_close_mode(row.open_status, close_permission or {}),
			})
	return result


def _close_permission(doc) -> dict:
	can_close = (
		cint(doc.docstatus) == 0
		and doc.get("against") == "YRP Work Order"
		and not doc.get("approved_by")
	)
	return get_close_permission() if can_close else {}


def work_order_close_mode(open_status, close_permission) -> str:
	has_approver = bool(close_permission.get("approver_role"))
	is_manager = bool(close_permission.get("is_close_manager"))
	if open_status == "Open" and is_manager:
		return "close"
	if open_status == "Open" and has_approver:
		return "request_close"
	if open_status == "Close Request" and is_manager:
		return "approve_close"
	return ""


def purchase_invoice_actions(doc, permissions, context) -> dict:
	docstatus = cint(doc.docstatus)
	is_sync_enabled = bool(context.get("erp_sync_enabled"))
	has_erp_invoice = bool(doc.get("erp_inv_name"))
	conditions = {
		"edit": docstatus == 0 and permissions.get("can_write"),
		"submit": docstatus == 0 and permissions.get("can_submit"),
		"approve": docstatus == 0 and doc.get("against") == "YRP Work Order"
		and not doc.get("approved_by") and permissions.get("can_write"),
		"fetch_expense_head": is_sync_enabled and docstatus == 0
		and bool(doc.get("items")) and permissions.get("can_create"),
		"show_erp_bill": docstatus == 1 and has_erp_invoice,
		"submit_erp_bill": is_sync_enabled and docstatus == 1 and has_erp_invoice
		and cint(doc.get("erp_inv_docstatus")) == 0 and permissions.get("can_submit"),
		"cancel": docstatus == 1 and permissions.get("can_cancel"),
		"amend": docstatus == 2 and permissions.get("can_amend"),
		"delete": docstatus == 0 and permissions.get("can_delete"),
	}
	reason = _("This action is not available for the current document state or your permissions.")
	return {key: action(allowed, ACTION_LABELS[key], reason) for key, allowed in conditions.items()}


def _serialize_rows(rows) -> list:
	return [row.as_dict() if isinstance(row, BaseDocument) else dict(row) for row in rows or []]


def _serialize_approvals(doc) -> list[dict]:
	return [
		{
			"user": row.get("user"),
			"approved_time": row.get("approved_time"),
			"comments": row.get("comments"),
		}
		for row in doc.get("purchase_invoice_wo_approval_details") or []
	]


def _totals(doc) -> list[dict]:
	return [
		{"key": fieldname, "label": label, "value": doc.get(fieldname)}
		for fieldname, label in TOTAL_FIELDS
	]


def _verification_details(doc) -> list:
	if doc.get("against") != "YRP Work Order":
		return []
	return build_verification_details(doc.get("pi_work_order_billed_details") or [])


def _debit_summary(doc) -> list:
	work_orders = sorted(_work_order_names(doc))
	if not work_orders or not frappe.db.exists("DocType", "YRP Debit"):
		return []
	return frappe.get_all(
		"YRP Debit",
		filters={"work_order": ["in", work_orders], "docstatus": 1},
		fields=[
			"name",
			"work_order",
			"debit_no",
			"debit_value",
			"reason",
			"inspection",
			"on_close",
			"status",
		],
		order_by="creation asc",
	)


@frappe.whitelist()
def get_purchase_invoice_workspace(name: str) -> dict:
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	permissions = permission_flags(DOCTYPE, PERMISSION_TYPES, doc)
	erp_sync_enabled = bool(is_erp_purchase_invoice_available())
	capabilities = purchase_invoice_actions(doc, permissions, {"erp_sync_enabled": erp_sync_enabled})
	print_formats = get_document_print_formats(doc)
	close_permission = _close_permission(doc)
	duplicate_billing_supplier = apply_purchase_invoice_response_permissions(doc)
	return {
		"record": _record(doc),
		"details": serialize_purchase_invoice_details(doc, duplicate_billing_supplier),
		"totals": _totals(doc),
		"items": serialize_grouped_items(doc),
		"grns": serialize_grns(doc),
		"verification": _serialize_rows(_verification_details(doc)),
		"debit_summary": _serialize_rows(_debit_summary(doc)),
		"approvals": _serialize_approvals(doc),
		"work_orders": serialize_work_orders(doc, close_permission),
		"permissions": permissions,
		"capabilities": capabilities,
		"print_formats": print_formats,
		"erp_sync_enabled": erp_sync_enabled,
	}
