# Copyright (c) 2026, anas@essdee.fit and contributors
"""Transfer a submitted YRP GRN's finished cloth into the MRP bench.

The operator starts the transfer from YRP. One local Material Issue clears the
finished cloth received by the GRN and one remote MRP Material Receipt creates
the corresponding stock. The source GRN stores both references. Creation is
idempotent per GRN, and cancelling the GRN reverses both Stock Entries first.
"""

import json
import re

import frappe
import requests
from frappe import _
from frappe.utils import flt, synchronization

REQUEST_TIMEOUT = 60


def _lock_name(grn_name):
	return "yrp_to_mrp_grn_" + re.sub(r"[^A-Za-z0-9_-]", "_", str(grn_name))


def _get_settings():
	settings = frappe.get_single("MRP Settings")
	site_url = (settings.get("mrp_site_url") or "").strip().rstrip("/")
	api_key = (settings.get("mrp_api_key") or "").strip()
	api_secret = settings.get_password("mrp_api_secret", raise_exception=False) or ""
	if not (site_url and api_key and api_secret):
		frappe.throw(
			_("Configure MRP Site URL, API Key, and API Secret in MRP Settings before creating MRP stock.")
		)
	return site_url, {"Authorization": f"token {api_key}:{api_secret}"}


def _response_error(response):
	try:
		body = response.json() or {}
	except ValueError:
		return _("MRP returned HTTP {0} with a non-JSON response.").format(response.status_code)

	server_messages = body.get("_server_messages")
	if isinstance(server_messages, str):
		try:
			server_messages = json.loads(server_messages)
		except TypeError, ValueError:
			server_messages = [server_messages]
	if server_messages:
		messages = []
		for raw in server_messages:
			try:
				msg = json.loads(raw).get("message")
			except TypeError, ValueError, AttributeError:
				msg = raw
			if msg:
				messages.append(frappe.utils.strip_html(str(msg)))
		if messages:
			return " ".join(messages)

	return frappe.utils.strip_html(
		str(body.get("exception") or body.get("message") or body.get("exc") or response.text)
	)


def _request(method, path, *, params=None, data=None):
	site_url, headers = _get_settings()
	try:
		response = requests.request(
			method,
			f"{site_url}{path}",
			headers={**headers, "Accept": "application/json", "Content-Type": "application/json"},
			params=params,
			json=data,
			timeout=REQUEST_TIMEOUT,
		)
	except requests.RequestException as exc:
		frappe.throw(_("Could not reach MRP ({0}). Nothing was transferred.").format(exc))

	if response.status_code < 200 or response.status_code >= 300:
		frappe.throw(
			_("MRP rejected the stock transfer: {0} Nothing was transferred.").format(
				_response_error(response)
			)
		)
	try:
		return response.json() or {}
	except ValueError:
		frappe.throw(_("MRP returned an invalid response. Nothing was transferred."))


def _remote_get(doctype, name):
	response = _request("GET", f"/api/resource/{doctype}/{requests.utils.quote(str(name), safe='')}")
	return response.get("data") or {}


def _remote_exists(doctype, name):
	response = _request(
		"GET",
		f"/api/resource/{doctype}",
		params={
			"filters": json.dumps([["name", "=", name]]),
			"fields": json.dumps(["name"]),
			"limit_page_length": 1,
		},
	)
	return bool(response.get("data"))


def _find_remote_receipt(grn_name):
	response = _request(
		"GET",
		"/api/resource/Stock Entry",
		params={
			"filters": json.dumps(
				[
					["purpose", "=", "Material Receipt"],
					["comments", "=", f"YRP GRN {grn_name}"],
				]
			),
			"fields": json.dumps(["name", "docstatus"]),
			"limit_page_length": 1,
		},
	)
	rows = response.get("data") or []
	return rows[0] if rows else None


def _validate_grn(doc):
	frappe.has_permission("Goods Received Note", "write", doc=doc, throw=True)
	if doc.docstatus != 1:
		frappe.throw(_("Goods Received Note must be submitted before creating MRP stock."))
	if doc.against != "Work Order":
		frappe.throw(_("Only Work Order Goods Received Notes can create MRP stock."))
	if doc.get("mrp_stock_entry_created"):
		frappe.throw(
			_("MRP stock was already created in Stock Entry {0}.").format(doc.get("mrp_stock_entry") or "?")
		)
	if doc.get("is_internal_unit") and not doc.get("transfer_complete"):
		frappe.throw(_("Complete the internal GRN transfer before creating MRP stock."))
	if not doc.get("to_warehouse"):
		frappe.throw(_("The Goods Received Note has no target warehouse to issue from."))
	if not doc.get("delivery_location"):
		frappe.throw(_("The Goods Received Note has no Delivery Location for the MRP receipt."))


def _source_rows(doc):
	rows = [row for row in (doc.get("items") or []) if flt(row.quantity) > 0]
	if not rows:
		frappe.throw(_("No positive Goods Received Note items are available to transfer."))
	return rows


def _validate_remote_masters(doc, rows):
	checks = {
		"Supplier": {doc.delivery_location},
		"Item Variant": {row.item_variant for row in rows if row.item_variant},
		"Lot": {row.get("lot") for row in rows if row.get("lot")},
		"UOM": {row.uom for row in rows if row.uom},
		"GRN Item Type": {(row.get("received_type") or "Accepted") for row in rows},
	}
	for doctype, names in checks.items():
		missing = [name for name in sorted(names) if not _remote_exists(doctype, name)]
		if missing:
			frappe.throw(
				_("{0} missing in MRP: {1}. Nothing was transferred.").format(doctype, ", ".join(missing))
			)


def _make_local_issue(doc, rows):
	issue = frappe.new_doc("Stock Entry")
	issue.purpose = "Material Issue"
	issue.against = "Goods Received Note"
	issue.against_id = doc.name
	issue.from_warehouse = doc.to_warehouse
	issue.comments = _("MRP transfer for YRP GRN {0}").format(doc.name)
	for index, row in enumerate(rows):
		values = {
			"item": row.item_variant,
			"qty": flt(row.quantity),
			"uom": row.uom,
			"conversion_factor": flt(row.get("conversion_factor")) or 1,
			"rate": flt(row.get("rate")),
			"row_index": index,
			"table_index": 0,
			"remarks": _("MRP transfer for YRP GRN {0}").format(doc.name),
		}
		for fieldname in ("lot", "received_type"):
			if row.get(fieldname):
				values[fieldname] = row.get(fieldname)
		issue.append("items", values)
	issue.insert(ignore_permissions=True)
	issue.submit()
	return issue


def _build_mrp_item_details(rows):
	"""Build the grouped payload expected by the Frappe 15 MRP Stock Entry.

	MRP's controller intentionally rebuilds its hidden ``items`` child table
	from ``item_details`` during ``before_validate``. Sending child rows alone
	therefore produces an empty Stock Entry. Keep one grouped UI row per exact
	variant so no colour/Dia quantity can be merged accidentally.
	"""
	groups = []
	for index, row in enumerate(rows):
		variant = frappe.get_cached_doc("Item Variant", row.item_variant)
		attribute_values = {
			attribute.attribute: attribute.attribute_value for attribute in (variant.get("attributes") or [])
		}
		primary_attribute = frappe.get_cached_value("Item", variant.item, "primary_attribute") or ""
		primary_value = attribute_values.pop(primary_attribute, None) if primary_attribute else None
		value = {
			"qty": flt(row.quantity),
			"rate": flt(row.get("rate")),
			"secondary_qty": flt(row.get("secondary_qty")),
			"secondary_uom": row.get("secondary_uom"),
			"set_combination": {},
		}
		values = {primary_value: value} if primary_attribute and primary_value else {"default": value}
		groups.append(
			{
				"attributes": list(attribute_values),
				"primary_attribute": primary_attribute or None,
				"primary_attribute_values": [primary_value] if primary_value else [],
				"items": [
					{
						"name": variant.item,
						"lot": row.get("lot"),
						"attributes": attribute_values,
						"primary_attribute": primary_attribute or None,
						"values": values,
						"default_uom": row.uom,
						"secondary_uom": row.get("secondary_uom"),
						"received_type": row.get("received_type") or "Accepted",
						"remarks": f"YRP GRN {row.parent}",
						"row_index": index,
					}
				],
			}
		)
	return groups


def _create_remote_receipt(doc, rows):
	remote_doc = {
		"doctype": "Stock Entry",
		"purpose": "Material Receipt",
		"to_warehouse": doc.delivery_location,
		"comments": f"YRP GRN {doc.name}",
		"item_details": _build_mrp_item_details(rows),
	}

	created = _request("POST", "/api/resource/Stock Entry", data=remote_doc).get("data") or {}
	if not created.get("name"):
		frappe.throw(_("MRP did not return the created Stock Entry name. Nothing was transferred."))
	return _submit_remote_receipt(created)


def _submit_remote_receipt(remote_doc):
	submitted = _request(
		"POST",
		"/api/method/frappe.client.submit",
		data={"doc": remote_doc},
	)
	result = submitted.get("message") or remote_doc
	return result.get("name") or remote_doc["name"]


def _ensure_remote_receipt(remote, doc, rows):
	"""Create a receipt or resume a draft left by an interrupted prior attempt."""
	if not remote:
		return _create_remote_receipt(doc, rows)
	status = int(remote.get("docstatus") or 0)
	if status == 2:
		frappe.throw(
			_("The previous MRP receipt for this GRN is cancelled. Amend the GRN before transferring again.")
		)
	if status == 0:
		return _submit_remote_receipt(_remote_get("Stock Entry", remote.get("name")))
	return remote.get("name")


@frappe.whitelist()
def create_mrp_stock(grn_name):
	"""Create the local issue and remote MRP receipt for a submitted YRP GRN."""
	doc = frappe.get_doc("Goods Received Note", grn_name)
	_validate_grn(doc)

	with synchronization.filelock(_lock_name(grn_name), timeout=60):
		# Re-read inside the lock so concurrent requests cannot both pass the flag.
		doc.reload()
		_validate_grn(doc)
		rows = _source_rows(doc)
		_validate_remote_masters(doc, rows)

		remote = _find_remote_receipt(grn_name)
		if remote and int(remote.get("docstatus") or 0) == 2:
			frappe.throw(
				_(
					"The previous MRP receipt for this GRN is cancelled. Amend the GRN before transferring again."
				)
			)

		issue_name = frappe.db.get_value(
			"Stock Entry",
			{
				"against": "Goods Received Note",
				"against_id": grn_name,
				"purpose": "Material Issue",
				"docstatus": 1,
			},
			"name",
		)
		issue = frappe.get_doc("Stock Entry", issue_name) if issue_name else _make_local_issue(doc, rows)
		remote_name = _ensure_remote_receipt(remote, doc, rows)

		frappe.db.set_value(
			"Goods Received Note",
			grn_name,
			{
				"mrp_stock_entry_created": 1,
				"mrp_stock_entry": remote_name,
				"yrp_material_issue": issue.name,
			},
			update_modified=False,
		)
		return {
			"ok": True,
			"mrp_stock_entry": remote_name,
			"yrp_material_issue": issue.name,
			"duplicate": bool(remote),
		}


def _cancel_remote_receipt(name):
	remote_doc = _remote_get("Stock Entry", name)
	if int(remote_doc.get("docstatus") or 0) == 2:
		return
	if int(remote_doc.get("docstatus") or 0) != 1:
		frappe.throw(_("MRP Stock Entry {0} is not submitted and cannot be reversed safely.").format(name))
	_request(
		"POST",
		"/api/method/frappe.client.cancel",
		data={"doctype": "Stock Entry", "name": name},
	)


def before_grn_cancel(doc, method=None):
	"""Reverse both transfer Stock Entries before the source GRN can cancel."""
	if not doc.get("mrp_stock_entry_created"):
		return
	frappe.has_permission("Goods Received Note", "cancel", doc=doc, throw=True)
	with synchronization.filelock(_lock_name(doc.name), timeout=60):
		remote_name = doc.get("mrp_stock_entry")
		issue_name = doc.get("yrp_material_issue")

		# Clear the submitted GRN's Link field before cancelling its local
		# Material Issue; otherwise Frappe correctly blocks cancellation because
		# the submitted GRN still points at that Stock Entry. These writes share
		# the GRN cancellation transaction and roll back if a later step fails.
		frappe.db.set_value(
			"Goods Received Note",
			doc.name,
			{
				"mrp_stock_entry_created": 0,
				"mrp_stock_entry": None,
				"yrp_material_issue": None,
			},
			update_modified=False,
		)
		doc.mrp_stock_entry_created = 0
		doc.mrp_stock_entry = None
		doc.yrp_material_issue = None

		if issue_name and frappe.db.exists("Stock Entry", issue_name):
			issue = frappe.get_doc("Stock Entry", issue_name)
			if issue.docstatus == 1:
				issue.cancel()

		# Cross the site boundary only after all local reversal validations pass.
		if remote_name:
			_cancel_remote_receipt(remote_name)
