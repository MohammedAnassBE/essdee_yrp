"""Essdee Purchase Invoice bridge to the existing ERP-side MRP API."""

from __future__ import annotations

import urllib.parse

import frappe
from frappe import _
from frappe.utils import cint, flt
from yrp.yrp.doctype.yrp_purchase_invoice.yrp_purchase_invoice import _get_tax_rate

from essdee_yrp.erp import (
	get_erp_response_message,
	get_erp_site_url,
	get_purchase_invoice_series,
	is_purchase_invoice_sync_active,
	post_erp_request,
)


CREATE_ENDPOINT = "/api/method/essdee.essdee.utils.mrp.purchase_invoice.create"
SUBMIT_ENDPOINT = "/api/method/essdee.essdee.utils.mrp.purchase_invoice.submit"
CANCEL_ENDPOINT = "/api/method/essdee.essdee.utils.mrp.purchase_invoice.cancel"
EXPENSE_ACCOUNT_ENDPOINT = (
	"/api/method/essdee.essdee.utils.mrp.purchase_invoice.get_erp_item_expense_account"
)
MAX_EXPENSE_ACCOUNT_ITEMS = 200


def build_erp_invoice_payload(invoice):
	"""Translate the F16 invoice into the legacy ERP API's exact data contract."""
	data = invoice.as_dict(convert_dates_to_str=True)
	# Every Essdee-projected invoice sends the operator-facing grouped bill.
	# ``items`` is the hidden direct-GRN valuation projection in that flow.
	rows = invoice.get("essdee_items") or invoice.get("items") or []
	data["items"] = [_erp_item(row) for row in rows]
	# The ERP endpoint still reads this production_api-era key. F16 YRP owns the
	# same relationship as Purchase Invoice.bill_tracking.
	data["vendor_bill_tracking"] = invoice.get("bill_tracking")
	data.pop("bill_tracking", None)
	data.pop("essdee_items", None)
	data.pop("essdee_rate_table_source", None)

	mapped_series = get_purchase_invoice_series(invoice.naming_series)
	if mapped_series:
		data["mapped_series"] = mapped_series
	else:
		data.pop("mapped_series", None)
	return data


def _erp_item(row):
	return {
		"item": row.get("item"),
		"lot": row.get("lot"),
		"item_group": row.get("item_group"),
		"expense_head": row.get("expense_head"),
		"qty": flt(row.get("qty")),
		"uom": row.get("uom"),
		"rate": flt(row.get("rate")),
		"amount": flt(row.get("qty")) * flt(row.get("rate")),
		# ERP's existing endpoint expects the percentage, while F16 stores a
		# Link to Tax Slab. Essdee's migrated Tax Slab names are numeric, but
		# resolving the percentage keeps this correct for future named slabs.
		"tax": _get_tax_rate(row.get("tax")),
	}


def fetch_expense_accounts(items, *, raise_on_error=False):
	"""Populate ERP expense heads once per distinct Process/PO billing Item."""
	rows = [dict(row) for row in (items or [])]
	if not is_purchase_invoice_sync_active():
		return rows

	accounts = {}
	for row in rows:
		item = row.get("item")
		if not item or item in accounts:
			continue
		response = post_erp_request(EXPENSE_ACCOUNT_ENDPOINT, {"item": item})
		accounts[item] = get_erp_response_message(
			response,
			title=f"Purchase Invoice Expense Account Fetch - {item}",
			raise_on_error=raise_on_error,
		)
	for row in rows:
		row["expense_head"] = accounts.get(row.get("item"))
	return rows


@frappe.whitelist()
def fetch_items_expense_head(items):
	frappe.has_permission('YRP Purchase Invoice', "create", throw=True)
	items = frappe.parse_json(items) if isinstance(items, str) else items
	if not isinstance(items, list):
		frappe.throw(_("Purchase Invoice Items must be a list."))
	if len(items) > MAX_EXPENSE_ACCOUNT_ITEMS:
		frappe.throw(
			_("A maximum of {0} Items can be fetched at once.").format(
				MAX_EXPENSE_ACCOUNT_ITEMS
			)
		)
	for row in items:
		if not isinstance(row, dict):
			frappe.throw(_("Invalid Purchase Invoice Item details."))
		item = row.get("item")
		if item and (not isinstance(item, str) or len(item) > 140):
			frappe.throw(_("Invalid Purchase Invoice Item."))
	if not is_purchase_invoice_sync_active():
		frappe.throw(_("Purchase Invoice ERP Sync is not enabled in MRP Settings."))
	return fetch_expense_accounts(items, raise_on_error=True)


def create_erp_invoice(invoice):
	if not is_purchase_invoice_sync_active():
		return None
	response = post_erp_request(CREATE_ENDPOINT, {"data": build_erp_invoice_payload(invoice)})
	message = get_erp_response_message(
		response,
		title=f"Purchase Invoice ERP Create - {invoice.name}",
	)
	_apply_erp_result(invoice, message)
	return message


@frappe.whitelist()
def submit_erp_invoice(name):
	if not is_purchase_invoice_sync_active():
		frappe.throw(_("Purchase Invoice ERP Sync is not enabled in MRP Settings."))
	invoice = frappe.get_doc('YRP Purchase Invoice', name)
	frappe.has_permission('YRP Purchase Invoice', "submit", doc=invoice, throw=True)
	if invoice.docstatus == 0:
		frappe.throw(_("Document is not submitted."))
	if invoice.docstatus == 2:
		frappe.throw(_("Document is already cancelled."))
	if not invoice.erp_inv_name:
		frappe.throw(_("ERP Purchase Invoice has not been created."))
	if cint(invoice.erp_inv_docstatus) != 0:
		frappe.throw(
			_("ERP Purchase Invoice {0} is already submitted.").format(invoice.erp_inv_name)
		)

	response = post_erp_request(SUBMIT_ENDPOINT, {"name": invoice.erp_inv_name})
	message = get_erp_response_message(
		response,
		title=f"Purchase Invoice ERP Submit - {invoice.name}",
	)
	_apply_erp_result(invoice, message)
	frappe.db.set_value(
		'YRP Purchase Invoice',
		invoice.name,
		{
			"erp_inv_name": invoice.erp_inv_name,
			"erp_inv_docstatus": invoice.erp_inv_docstatus,
			"final_amount": invoice.final_amount,
			"due_date": invoice.due_date,
		},
	)
	return message


def cancel_erp_invoice(invoice):
	if (
		not is_purchase_invoice_sync_active()
		or invoice.get("cancel_without_cancelling_erp_inv")
		or not invoice.get("erp_inv_name")
		or cint(invoice.get("erp_inv_docstatus")) == 2
	):
		return None

	response = post_erp_request(CANCEL_ENDPOINT, {"name": invoice.erp_inv_name})
	get_erp_response_message(
		response,
		title=f"Purchase Invoice ERP Cancel - {invoice.name}",
		allow_empty=True,
	)
	invoice.erp_inv_docstatus = 2
	return True


@frappe.whitelist()
def get_erp_inv_link(name):
	invoice = frappe.get_doc('YRP Purchase Invoice', name)
	frappe.has_permission('YRP Purchase Invoice', "read", doc=invoice, throw=True)
	if invoice.docstatus != 1 or not invoice.erp_inv_name:
		frappe.throw(_("ERP Purchase Invoice is not available."))
	return (
		f"{get_erp_site_url()}/app/purchase-invoice/"
		f"{urllib.parse.quote(invoice.erp_inv_name, safe='')}"
	)


@frappe.whitelist()
def close_bill_tracking_from_erp(name, purchase_invoice, remarks=None):
	"""Adapt the ERP's production_api callback to F16 Bill Tracking.

	The legacy callback sends the ERP Purchase Invoice name. F16 keeps its Bill
	Tracking link pointed at the local YRP Purchase Invoice; the ERP name is
	stored on that local invoice instead.
	"""
	bill = frappe.get_doc('YRP Bill Tracking', name)
	bill.check_permission("write")
	local_invoice = _local_invoice_for_erp_callback(name, purchase_invoice)
	if bill.form_status == "Closed":
		if bill.purchase_invoice == local_invoice:
			return
		frappe.throw(
			_("Bill Tracking {0} is already closed against {1}.").format(
				name, bill.purchase_invoice
			)
		)
	bill.close_vendor_bill(local_invoice, remarks)
	bill.save(ignore_permissions=True)


@frappe.whitelist()
def revert_bill_tracking_from_erp(
	name,
	pi_field,
	expected_pi_name,
	origin=None,
):
	"""Adapt the ERP cancellation callback without clobbering a replacement PI."""
	if pi_field not in {"purchase_invoice", "mrp_purchase_invoice"}:
		frappe.throw(_("Invalid Purchase Invoice field: {0}.").format(pi_field))
	bill = frappe.get_doc('YRP Bill Tracking', name)
	bill.check_permission("write")
	local_invoice = (
		expected_pi_name
		if pi_field == "mrp_purchase_invoice"
		else _local_invoice_for_erp_callback(name, expected_pi_name)
	)
	if not bill.purchase_invoice and bill.form_status != "Closed":
		return
	from yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking import revert_purchase_invoice_link

	revert_purchase_invoice_link(name, local_invoice, origin=origin or "ERP-cancel")


def _local_invoice_for_erp_callback(bill_tracking, erp_invoice):
	local_invoice = frappe.db.get_value(
		'YRP Purchase Invoice',
		{
			"bill_tracking": bill_tracking,
			"erp_inv_name": erp_invoice,
			"docstatus": ["!=", 2],
		},
		"name",
	)
	if not local_invoice:
		# During ERP creation the local submit transaction has not received and
		# persisted erp_inv_name yet. The already-saved active draft is still the
		# authoritative owner of this Bill Tracking row.
		local_invoice = frappe.db.get_value(
			'YRP Purchase Invoice',
			{"bill_tracking": bill_tracking, "docstatus": ["!=", 2]},
			"name",
			order_by="modified desc",
		)
	if not local_invoice:
		frappe.throw(
			_("No active local Purchase Invoice was found for Bill Tracking {0}.").format(
				bill_tracking
			)
		)
	return local_invoice


def _apply_erp_result(invoice, result):
	if not isinstance(result, dict):
		frappe.throw(_("ERP returned an invalid Purchase Invoice response."))
	missing = [field for field in ("name", "docstatus", "amount", "due_date") if field not in result]
	if missing:
		frappe.throw(
			_("ERP Purchase Invoice response is missing: {0}.").format(", ".join(missing))
		)
	invoice.update(
		{
			"erp_inv_name": result["name"],
			"erp_inv_docstatus": result["docstatus"],
			"final_amount": result["amount"],
			"due_date": result["due_date"],
		}
	)
