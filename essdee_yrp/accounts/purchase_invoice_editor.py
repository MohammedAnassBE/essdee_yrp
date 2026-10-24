from collections.abc import Mapping

import frappe
from frappe import _
from frappe.utils import cint
from yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice import _get_tax_rate

from essdee_yrp.accounts.purchase_invoice_workspace import (
	PERMISSION_TYPES,
	apply_purchase_invoice_response_permissions,
	get_purchase_invoice_workspace,
	purchase_invoice_actions,
	serialize_grouped_items,
)
from essdee_yrp.api.duplicate import build_duplicate_values
from essdee_yrp.erp_purchase_invoice import is_erp_purchase_invoice_available
from essdee_yrp.purchase_invoice import MIGRATED_RATE_SOURCE, MODERN_RATE_SOURCE
from essdee_yrp.web_common import (
	assert_expected_modified,
	is_masked_value,
	parse_mapping,
	permission_flags,
	value,
)

DOCTYPE = "YRP Purchase Invoice"
BILL_TRACKING_DOCTYPE = "YRP Bill Tracking"
ITEM_DOCTYPE = "SD YRP Essdee Purchase Invoice Item"
EDITOR_FIELDS = (
	"supplier",
	"against",
	"posting_date",
	"posting_time",
	"due_date",
	"do_not_submit_invoice",
	"bill_no",
	"billing_supplier",
	"bill_date",
	"eligibility_for_itc",
	"debit_type",
	"debit_no",
	"debit_value",
	"remarks",
)
EDITOR_DISPLAY_FIELDS = ("gstin", "pan_no", "status", "amended_from")
LOCKED_BILL_TRACKING_FIELDS = ["supplier", "bill_no", "bill_date"]
MASKED_EDITOR_FIELDS = {"supplier", "billing_supplier"}
COMMAND_PERMISSIONS = {
	"submit": "submit",
	"cancel": "cancel",
	"amend": "amend",
	"delete": "delete",
}


def _parse_list(value, label: str) -> list:
	if isinstance(value, str):
		value = frappe.parse_json(value)
	if not isinstance(value, list):
		frappe.throw(_("{0} must be a list.").format(label))
	return value


def _parse_item_rows(value) -> list[dict]:
	rows = _parse_list(value, _("Grouped items"))
	if any(not isinstance(row, Mapping) for row in rows):
		frappe.throw(_("Grouped item rows must be objects."))
	return [dict(row) for row in rows]


def _field_schema(doc, fieldname: str) -> dict:
	field = doc.meta.get_field(fieldname)
	if not field:
		frappe.throw(_("Purchase Invoice field {0} is not configured.").format(fieldname))
	return {
		"label": field.label or fieldname.replace("_", " ").title(),
		"fieldtype": field.fieldtype,
		"options": field.options,
		"reqd": bool(field.reqd),
		"read_only": bool(field.read_only),
	}


def _editor_items(doc) -> list[dict]:
	items = serialize_grouped_items(doc)
	for item in items:
		item["tax_rate"] = _get_tax_rate(item.get("tax"))
	return items


def _editor_payload(doc, is_existing: bool, duplicate_billing_supplier: bool) -> dict:
	fieldnames = (*EDITOR_FIELDS, *EDITOR_DISPLAY_FIELDS, "bill_tracking")
	bill_tracking = doc.get("bill_tracking")
	rate_source = doc.get("essdee_rate_table_source")
	values = {fieldname: doc.get(fieldname) for fieldname in fieldnames}
	if duplicate_billing_supplier:
		values["billing_supplier"] = values["supplier"]
	return {
		"values": values,
		"grns": [row.get("grn") for row in doc.get("grn") or [] if row.get("grn")],
		"items": _editor_items(doc),
		"essdee_rate_table_source": rate_source,
		"is_rate_only": rate_source == MIGRATED_RATE_SOURCE,
		"modified": doc.get("modified") if is_existing else None,
		"locked_fields": LOCKED_BILL_TRACKING_FIELDS if bill_tracking else [],
		"schema": {
			fieldname: _field_schema(doc, fieldname)
			for fieldname in (*EDITOR_FIELDS, *EDITOR_DISPLAY_FIELDS)
		},
	}


def _get_available_bill_tracking(bill_tracking: str, *, for_update: bool = False):
	bill = frappe.get_doc(BILL_TRACKING_DOCTYPE, bill_tracking, for_update=for_update)
	bill.check_permission("read")
	if bill.get("purchase_invoice") or bill.get("erp_purchase_invoice"):
		frappe.throw(_("Bill Tracking {0} is already linked to an invoice.").format(bill.name))
	return bill


def new_purchase_invoice_from_bill_tracking(bill_tracking: str, *, for_update: bool = False):
	bill = _get_available_bill_tracking(bill_tracking, for_update=for_update)
	doc = frappe.new_doc(DOCTYPE)
	for fieldname, field_value in {
		"supplier": bill.get("supplier"),
		"billing_supplier": bill.get("supplier"),
		"bill_date": bill.get("bill_date"),
		"bill_no": bill.get("bill_no"),
		"bill_tracking": bill.name,
	}.items():
		doc.set(fieldname, field_value)
	return doc


@frappe.whitelist()
def get_purchase_invoice_editor(
	name: str | None = None, bill_tracking: str | None = None, duplicate_from: str | None = None
) -> dict:
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		doc.check_permission("write")
		if cint(doc.docstatus) != 0:
			frappe.throw(_("Only a draft Purchase Invoice can be edited."))
		duplicate_billing_supplier = apply_purchase_invoice_response_permissions(doc)
		return _editor_payload(doc, True, duplicate_billing_supplier)

	frappe.has_permission(DOCTYPE, ptype="create", throw=True)
	if duplicate_from:
		doc = frappe.get_doc(build_duplicate_values(DOCTYPE, duplicate_from))
		doc.set("bill_tracking", None)
	elif bill_tracking:
		doc = new_purchase_invoice_from_bill_tracking(bill_tracking)
	else:
		doc = frappe.new_doc(DOCTYPE)
	duplicate_billing_supplier = apply_purchase_invoice_response_permissions(doc)
	return _editor_payload(doc, False, duplicate_billing_supplier)


def apply_editor_values(doc, values: Mapping) -> None:
	for fieldname in EDITOR_FIELDS:
		if fieldname not in values:
			continue
		if fieldname in MASKED_EDITOR_FIELDS and is_masked_value(values[fieldname]):
			continue
		doc.set(fieldname, values[fieldname])


def _set_row_value(row, fieldname, value) -> None:
	setter = getattr(row, "set", None)
	if callable(setter):
		setter(fieldname, value)
	elif isinstance(row, dict):
		row[fieldname] = value
	else:
		setattr(row, fieldname, value)


def _update_grouped_items_in_place(stored_rows, posted_rows) -> None:
	posted_by_key = {row.get("group_key"): row for row in posted_rows}
	for stored_row in stored_rows:
		posted = posted_by_key[value(stored_row, "group_key")]
		if "rate" in posted:
			_set_row_value(stored_row, "rate", posted["rate"])
		if "expense_head" in posted:
			_set_row_value(stored_row, "expense_head", posted["expense_head"])


def apply_grouped_items(doc, posted_rows: list[dict]) -> None:
	stored_rows = list(doc.get("essdee_items") or [])
	stored_keys = {value(row, "group_key") for row in stored_rows}
	posted_keys = {row.get("group_key") for row in posted_rows}
	if not posted_rows and not stored_rows:
		return
	if doc.get("essdee_rate_table_source") and posted_keys == stored_keys:
		_update_grouped_items_in_place(stored_rows, posted_rows)
		return

	allowed_fields = {field.fieldname for field in frappe.get_meta(ITEM_DOCTYPE).fields}
	filtered_rows = [
		{fieldname: value for fieldname, value in row.items() if fieldname in allowed_fields}
		for row in posted_rows
	]
	doc.set("essdee_items", filtered_rows)
	doc.set("essdee_rate_table_source", MODERN_RATE_SOURCE)


def _load_draft_for_save(name: str | None, expected_modified=None, bill_tracking=None):
	if not name:
		frappe.has_permission(DOCTYPE, ptype="create", throw=True)
		return (
			new_purchase_invoice_from_bill_tracking(bill_tracking, for_update=True)
			if bill_tracking
			else frappe.new_doc(DOCTYPE)
		)
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("write")
	if cint(doc.docstatus) != 0:
		frappe.throw(_("Only a draft Purchase Invoice can be saved."))
	assert_expected_modified(doc, expected_modified)
	return doc


def _actions(doc) -> dict:
	context = {"erp_sync_enabled": bool(is_erp_purchase_invoice_available())}
	return purchase_invoice_actions(doc, permission_flags(DOCTYPE, PERMISSION_TYPES, doc), context)


def _require_action(doc, command: str) -> None:
	capability = _actions(doc).get(command) or {}
	if not capability.get("allowed"):
		frappe.throw(
			capability.get("reason") or _("This Purchase Invoice action is not available."),
			frappe.PermissionError,
		)


@frappe.whitelist()
def save_purchase_invoice(
	values,
	grns,
	items,
	name: str | None = None,
	submit: bool = False,
	expected_modified=None,
) -> dict:
	values = parse_mapping(values, _("Purchase Invoice values"))
	grns = _parse_list(grns, _("GRNs"))
	items = _parse_item_rows(items)
	doc = _load_draft_for_save(name, expected_modified, values.get("bill_tracking"))
	apply_editor_values(doc, values)
	doc.set("grn", [{"grn": grn} for grn in dict.fromkeys(grns)])
	apply_grouped_items(doc, items)
	if name:
		doc.save()
	else:
		doc.insert()
	if cint(submit):
		_require_action(doc, "submit")
		doc.check_permission("submit")
		doc.submit()
	return get_purchase_invoice_workspace(doc.name)


def _cancel_purchase_invoice(doc, payload: Mapping) -> None:
	if doc.get("erp_inv_name"):
		doc.db_set(
			"cancel_without_cancelling_erp_inv",
			cint(payload.get("cancel_without_cancelling_erp_inv")),
		)
	doc.cancel()


def _amend_purchase_invoice(doc):
	amended = frappe.copy_doc(doc, ignore_no_copy=False)
	amended.docstatus = 0
	amended.set("amended_from", doc.name)
	amended.set("status", "Draft")
	if amended.get("bill_tracking"):
		_get_available_bill_tracking(amended.get("bill_tracking"), for_update=True)
	amended.insert()
	return amended


@frappe.whitelist()
def execute_purchase_invoice_command(
	name: str,
	command: str,
	payload=None,
	expected_modified=None,
) -> dict:
	if command not in COMMAND_PERMISSIONS:
		frappe.throw(_("Unsupported Purchase Invoice action: {0}").format(command))
	payload = parse_mapping(payload or {}, _("Action values"))
	doc = frappe.get_doc(DOCTYPE, name, for_update=True)
	assert_expected_modified(doc, expected_modified)
	_require_action(doc, command)
	doc.check_permission(COMMAND_PERMISSIONS[command])

	if command == "submit":
		doc.submit()
	elif command == "cancel":
		_cancel_purchase_invoice(doc, payload)
	elif command == "delete":
		frappe.delete_doc(DOCTYPE, name)
		return {"deleted": True, "record": {"name": name}}
	else:
		amended = _amend_purchase_invoice(doc)
		return get_purchase_invoice_workspace(amended.name)
	return get_purchase_invoice_workspace(name)
