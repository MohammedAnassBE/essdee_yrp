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


def is_same_site_erp_available():
	"""Return whether this site can create Essdee's ERPNext Purchase Invoice locally."""
	if getattr(frappe.flags, "in_test", False) and not getattr(
		frappe.flags, "allow_erp_purchase_invoice_sync_in_test", False
	):
		return False
	if "essdee" not in frappe.get_installed_apps():
		return False

	invoice_meta = frappe.get_meta("Purchase Invoice")
	item_meta = frappe.get_meta("Purchase Invoice Item")
	return all(
		(
			invoice_meta.has_field("mrp_purchase_invoice_name"),
			invoice_meta.has_field("vendor_bill_tracking"),
			item_meta.has_field("sd_lot"),
		)
	)


def is_erp_purchase_invoice_available():
	"""Expose one UI switch for local ERPNext and legacy remote ERP flows."""
	return is_same_site_erp_available() or is_purchase_invoice_sync_active()


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
	tax_rate = flt(_get_tax_rate(row.get("tax")))
	if tax_rate.is_integer():
		tax_rate = int(tax_rate)
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
		"tax": tax_rate,
	}


def fetch_expense_accounts(items, *, raise_on_error=False):
	"""Populate ERP expense heads once per distinct Process/PO billing Item."""
	rows = [dict(row) for row in (items or [])]
	use_same_site = is_same_site_erp_available()
	if not use_same_site and not is_purchase_invoice_sync_active():
		return rows

	accounts = {}
	for row in rows:
		item = row.get("item")
		if not item or item in accounts:
			continue
		if use_same_site:
			accounts[item] = _local_erp_purchase_invoice_api().get_erp_item_expense_account(item)
		else:
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
	if not is_erp_purchase_invoice_available():
		frappe.throw(_("ERP Purchase Invoice creation is not available on this site."))
	return fetch_expense_accounts(items, raise_on_error=True)


def create_erp_invoice(invoice):
	payload = build_erp_invoice_payload(invoice)
	if is_same_site_erp_available():
		message = _create_local_erp_invoice(payload)
		_apply_erp_result(invoice, message)
		return message
	if not is_purchase_invoice_sync_active():
		return None
	response = post_erp_request(CREATE_ENDPOINT, {"data": payload})
	message = get_erp_response_message(
		response,
		title=f"Purchase Invoice ERP Create - {invoice.name}",
	)
	_apply_erp_result(invoice, message)
	return message


@frappe.whitelist()
def submit_erp_invoice(name):
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

	if is_same_site_erp_available():
		message = _run_local_erp_action("submit", invoice.erp_inv_name)
	elif is_purchase_invoice_sync_active():
		response = post_erp_request(SUBMIT_ENDPOINT, {"name": invoice.erp_inv_name})
		message = get_erp_response_message(
			response,
			title=f"Purchase Invoice ERP Submit - {invoice.name}",
		)
	else:
		frappe.throw(_("ERP Purchase Invoice creation is not available on this site."))
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
		invoice.get("cancel_without_cancelling_erp_inv")
		or not invoice.get("erp_inv_name")
		or cint(invoice.get("erp_inv_docstatus")) == 2
	):
		return None

	if is_same_site_erp_available():
		_run_local_erp_action("cancel", invoice.erp_inv_name)
	elif is_purchase_invoice_sync_active():
		response = post_erp_request(CANCEL_ENDPOINT, {"name": invoice.erp_inv_name})
		get_erp_response_message(
			response,
			title=f"Purchase Invoice ERP Cancel - {invoice.name}",
			allow_empty=True,
		)
	else:
		return None
	invoice.erp_inv_docstatus = 2
	return True


@frappe.whitelist()
def get_erp_inv_link(name):
	invoice = frappe.get_doc('YRP Purchase Invoice', name)
	frappe.has_permission('YRP Purchase Invoice', "read", doc=invoice, throw=True)
	if invoice.docstatus != 1 or not invoice.erp_inv_name:
		frappe.throw(_("ERP Purchase Invoice is not available."))
	if is_same_site_erp_available():
		return f"/app/purchase-invoice/{urllib.parse.quote(invoice.erp_inv_name, safe='')}"
	return (
		f"{get_erp_site_url()}/app/purchase-invoice/"
		f"{urllib.parse.quote(invoice.erp_inv_name, safe='')}"
	)


def link_erp_invoice_to_bill_tracking(invoice):
	"""Store the same-site ERP invoice on Bill Tracking after YRP submit closes it."""
	if not invoice.get("bill_tracking") or not invoice.get("erp_inv_name"):
		return
	current = frappe.db.get_value(
		'YRP Bill Tracking', invoice.bill_tracking, "erp_purchase_invoice"
	)
	if current and current != invoice.erp_inv_name:
		frappe.throw(
			_("Bill Tracking {0} is already linked to ERP Purchase Invoice {1}.").format(
				invoice.bill_tracking, current
			)
		)
	frappe.db.set_value(
		'YRP Bill Tracking',
		invoice.bill_tracking,
		"erp_purchase_invoice",
		invoice.erp_inv_name,
		update_modified=False,
	)


def unlink_erp_invoice_from_bill_tracking(invoice):
	"""Clear only the ERP invoice link owned by the cancelling YRP invoice."""
	if not invoice.get("bill_tracking") or not invoice.get("erp_inv_name"):
		return
	if (
		frappe.db.get_value(
			'YRP Bill Tracking', invoice.bill_tracking, "erp_purchase_invoice"
		)
		== invoice.erp_inv_name
	):
		frappe.db.set_value(
			'YRP Bill Tracking',
			invoice.bill_tracking,
			"erp_purchase_invoice",
			None,
			update_modified=False,
		)


def _local_erp_purchase_invoice_api():
	from essdee.essdee.utils.mrp import purchase_invoice

	return purchase_invoice


def _create_local_erp_invoice(payload):
	"""Use Essdee's established creator without calling the retired remote MRP callback."""
	local_payload = dict(payload)
	local_payload["items"] = [dict(row) for row in payload.get("items") or []]
	bill_tracking = local_payload.get("vendor_bill_tracking")
	local_payload["vendor_bill_tracking"] = None
	api = _local_erp_purchase_invoice_api()
	_validate_local_erp_items(local_payload["items"], api)
	# Essdee's public ``create`` API validates an old cross-site contract where
	# the MRP Item Group was unprefixed and ERP added ``M_``. On the combined
	# site both rows already use the same ERPNext Item Group, so run the corrected
	# local validation above and retain its established document creator.
	result = api._create(local_payload)
	if bill_tracking and result and result.get("name"):
		frappe.db.set_value(
			"Purchase Invoice",
			result["name"],
			"vendor_bill_tracking",
			bill_tracking,
			update_modified=False,
		)
	return result


def _validate_local_erp_items(items, api):
	"""Validate same-site Items without applying the legacy MRP Item Group prefix."""
	exceptions = []
	seen = set()
	for row in items:
		item_code = row.get("item")
		if not item_code or item_code in seen:
			continue
		seen.add(item_code)
		if not frappe.db.exists("Item", item_code):
			exceptions.append(_("{0} does not exist").format(item_code))
			continue

		item_group = frappe.db.get_value("Item", item_code, "item_group")
		if item_group != row.get("item_group"):
			exceptions.append(
				_("For {0}, Item Group must be {1}, not {2}.").format(
					item_code,
					item_group,
					row.get("item_group") or _("blank"),
				)
			)
		if not api.get_erp_item_expense_account(item_code):
			exceptions.append(
				_("Item Group {0} for item {1} does not have a default Expense Account").format(
					item_group, item_code
				)
			)

	if exceptions:
		frappe.throw("<br>".join(exceptions))


def _run_local_erp_action(action, invoice_name):
	"""Submit/cancel locally while YRP owns the matching Bill Tracking lifecycle."""
	bill_tracking = frappe.db.get_value(
		"Purchase Invoice", invoice_name, "vendor_bill_tracking"
	)
	if bill_tracking:
		frappe.db.set_value(
			"Purchase Invoice",
			invoice_name,
			"vendor_bill_tracking",
			None,
			update_modified=False,
		)
	try:
		api = _local_erp_purchase_invoice_api()
		if action == "submit":
			return api.submit(invoice_name)
		if action == "cancel":
			api.cancel(invoice_name)
			return None
		frappe.throw(_("Unsupported ERP Purchase Invoice action: {0}.").format(action))
	finally:
		if bill_tracking and frappe.db.exists("Purchase Invoice", invoice_name):
			frappe.db.set_value(
				"Purchase Invoice",
				invoice_name,
				"vendor_bill_tracking",
				bill_tracking,
				update_modified=False,
			)


@frappe.whitelist()
def close_bill_tracking_from_erp(name, purchase_invoice, remarks=None):
	"""Close Bill Tracking from an ERPNext Purchase Invoice submission.

	A generated ERP invoice points back to a local YRP Purchase Invoice through
	``mrp_purchase_invoice_name``. A directly-created ERP invoice has no such
	link, so it closes Bill Tracking against ``erp_purchase_invoice`` alone.
	"""
	bill = frappe.get_doc('YRP Bill Tracking', name)
	bill.check_permission("write")
	same_site_invoice, local_invoice = _same_site_erp_invoice_context(
		name, purchase_invoice
	)
	if not same_site_invoice:
		local_invoice = _local_invoice_for_erp_callback(name, purchase_invoice)

	current_erp_invoice = bill.get("erp_purchase_invoice")
	if current_erp_invoice and current_erp_invoice != purchase_invoice:
		frappe.throw(
			_("Bill Tracking {0} is already linked to ERP Purchase Invoice {1}.").format(
				name, current_erp_invoice
			)
		)

	if bill.form_status == "Closed":
		if (
			local_invoice
			and bill.purchase_invoice == local_invoice
			and current_erp_invoice in (None, purchase_invoice)
		):
			if not current_erp_invoice:
				bill.erp_purchase_invoice = purchase_invoice
				bill.save(ignore_permissions=True)
			return
		if not local_invoice and current_erp_invoice == purchase_invoice:
			return
		frappe.throw(
			_("Bill Tracking {0} is already closed against {1}.").format(
				name, bill.purchase_invoice or current_erp_invoice
			)
		)

	if local_invoice:
		bill.erp_purchase_invoice = purchase_invoice
		bill.close_vendor_bill(local_invoice, remarks)
	else:
		if bill.purchase_invoice:
			frappe.throw(
				_("Bill Tracking {0} is already linked to YRP Purchase Invoice {1}.").format(
					name, bill.purchase_invoice
				)
			)
		if bill.docstatus != 1:
			frappe.throw(_("Bill Tracking must be submitted before it can be closed."))
		bill.append("bill_tracking_history", {
			"assigned_by": frappe.session.user,
			"assigned_on": frappe.utils.now_datetime(),
			"remarks": remarks,
			"action": "Close",
		})
		bill.form_status = "Closed"
		bill.erp_purchase_invoice = purchase_invoice
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
	if pi_field == "mrp_purchase_invoice":
		local_invoice = expected_pi_name
		same_site_invoice = False
	else:
		same_site_invoice, local_invoice = _same_site_erp_invoice_context(
			name, expected_pi_name
		)
		if not same_site_invoice:
			local_invoice = _local_invoice_for_erp_callback(name, expected_pi_name)

	if local_invoice:
		if bill.get("erp_purchase_invoice") == expected_pi_name:
			frappe.db.set_value(
				'YRP Bill Tracking',
				name,
				"erp_purchase_invoice",
				None,
				update_modified=False,
			)
		if not bill.purchase_invoice and bill.form_status != "Closed":
			return
		from yrp.yrp.doctype.yrp_bill_tracking.yrp_bill_tracking import revert_purchase_invoice_link

		revert_purchase_invoice_link(name, local_invoice, origin=origin or "ERP-cancel")
		return

	current_erp_invoice = bill.get("erp_purchase_invoice")
	if current_erp_invoice != expected_pi_name:
		frappe.log_error(
			title="Bill Tracking ERP revert skipped - PI mismatch",
			message=(
				f"Bill Tracking: {name}\n"
				f"Expected ERP PI: {expected_pi_name}\n"
				f"Current ERP PI: {current_erp_invoice}\n"
				f"Origin: {origin}"
			),
		)
		return
	bill.erp_purchase_invoice = None
	bill.append("bill_tracking_history", {
		"assigned_to": bill.assigned_to,
		"assigned_on": frappe.utils.now_datetime(),
		"assigned_by": frappe.session.user,
		"remarks": f"Auto-reverted: erp_purchase_invoice={expected_pi_name} ({origin or 'ERP-cancel'})",
		"action": "Reopen",
	})
	if bill.form_status == "Closed":
		bill.form_status = "Reopen"
	bill.save(ignore_permissions=True)


def _same_site_erp_invoice_context(bill_tracking, erp_invoice):
	"""Return whether the ERPNext invoice is local and its YRP PI, if any."""
	if not frappe.db.exists("Purchase Invoice", erp_invoice):
		return False, None
	context = frappe.db.get_value(
		"Purchase Invoice",
		erp_invoice,
		["vendor_bill_tracking", "mrp_purchase_invoice_name"],
		as_dict=True,
	)
	if not context:
		return True, None
	if context.vendor_bill_tracking and context.vendor_bill_tracking != bill_tracking:
		frappe.throw(
			_("ERP Purchase Invoice {0} belongs to Bill Tracking {1}.").format(
				erp_invoice, context.vendor_bill_tracking
			)
		)
	return True, context.mrp_purchase_invoice_name or None


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
