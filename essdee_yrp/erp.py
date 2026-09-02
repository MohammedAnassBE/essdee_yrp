"""Central ERP connection used by Essdee's MRP integrations."""

from __future__ import annotations

import json

import frappe
import requests
from frappe import _
from frappe.utils import cint


ERP_REQUEST_TIMEOUT = 120


def is_purchase_invoice_sync_enabled():
	"""Return the configured business switch without exposing credentials."""
	return bool(cint(frappe.db.get_single_value('SD YRP MRP Settings', "enable_purchase_invoice_sync")))


def is_purchase_invoice_sync_active():
	"""Keep test suites offline unless an ERP integration test opts in."""
	if getattr(frappe.flags, "in_test", False) and not getattr(
		frappe.flags, "allow_erp_purchase_invoice_sync_in_test", False
	):
		return False
	return is_purchase_invoice_sync_enabled()


def get_purchase_invoice_series(series):
	if not series:
		return None
	settings = frappe.get_single('SD YRP MRP Settings')
	for row in settings.get("purchase_invoice_series_map") or []:
		if row.series == series:
			return row.mapped_series
	return None


def get_erp_site_url():
	url = frappe.db.get_single_value('SD YRP MRP Settings', "erp_site_url")
	if not url:
		frappe.throw(_("Please configure ERP Site URL in MRP Settings."))
	return str(url).rstrip("/")


def post_erp_request(endpoint, data):
	"""Call the configured ERP using the existing token-authenticated contract."""
	if not is_purchase_invoice_sync_active():
		frappe.throw(_("Purchase Invoice ERP Sync is not enabled in MRP Settings."))

	settings = frappe.get_single('SD YRP MRP Settings')
	api_secret = settings.get_password("erp_api_secret")
	if not settings.erp_site_url or not settings.erp_api_key or not api_secret:
		frappe.throw(_("Please configure the ERP Site URL, API Key, and API Secret in MRP Settings."))

	url = f"{str(settings.erp_site_url).rstrip('/')}/{str(endpoint).lstrip('/')}"
	headers = {
		"Accept": "application/json",
		"Authorization": f"token {settings.erp_api_key}:{api_secret}",
	}
	try:
		return requests.post(
			url,
			headers=headers,
			json=data,
			timeout=ERP_REQUEST_TIMEOUT,
		)
	except requests.RequestException:
		frappe.log_error(
			title="Essdee ERP Request Error",
			message=frappe.get_traceback(),
		)
		frappe.throw(_("Could not connect to the configured ERP site."))


def get_erp_response_message(response, *, title, allow_empty=False, raise_on_error=True):
	"""Decode one ERP response and give every PI action the same error handling."""
	try:
		payload = response.json()
	except (TypeError, ValueError):
		payload = {}

	if response.status_code == 200 and (allow_empty or "message" in payload):
		return payload.get("message")

	message = (
		payload.get("exception")
		or payload.get("message")
		or payload.get("_server_messages")
		or getattr(response, "text", None)
		or _("ERP returned HTTP status {0}.").format(response.status_code)
	)
	frappe.log_error(
		title=title,
		message=json.dumps(payload, default=str) if payload else str(message),
	)
	if raise_on_error:
		# Remote exception text can contain HTML or implementation details. Keep
		# the complete response in Error Log, but return a stable local message.
		frappe.throw(_("The ERP request failed. Check Error Log for details."))
	return None
