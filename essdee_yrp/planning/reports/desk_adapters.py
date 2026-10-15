import frappe
from frappe import _
from frappe.desk.query_report import get_report_doc
from frappe.desk.query_report import run as run_query_report

from essdee_yrp.essdee_yrp.report.sd_yrp_work_order_pending_report.sd_yrp_work_order_pending_report import (
	get_report_summary,
)
from essdee_yrp.planning.reports.production_quantities import authorize_filter_values

WORK_ORDER = "SD YRP Work Order Report"
DISPATCH = "SD YRP Dispatch Percentage Report"
PENDING = "SD YRP Work Order Pending Report"
MULTI_FILTERS = {
	"lot": "SD YRP Lot", "item": "Item", "production_order": "YRP Production Order",
	"item_variant": "Item", "process": "YRP Process", "supplier": "Supplier",
}


def can_run_desk_report(report_name):
	if frappe.session.user == "Guest":
		return False
	try:
		report = get_report_doc(report_name)
	except (frappe.PermissionError, frappe.ValidationError, frappe.DoesNotExistError):
		return False
	return bool(frappe.has_permission(report.ref_doctype, "read"))


def require_access(report_name):
	if not can_run_desk_report(report_name):
		frappe.throw(_("You do not have access to this Planning report."), frappe.PermissionError)


def require_work_order_access():
	require_access(WORK_ORDER)


def require_dispatch_access():
	require_access(DISPATCH)


def require_pending_access():
	require_access(PENDING)


def _run(report_name, filters, multi_fields=()):
	require_access(report_name)
	filters = dict(filters or {})
	for field in multi_fields:
		if field in filters:
			filters[field] = authorize_filter_values(MULTI_FILTERS[field], filters[field])
	payload = run_query_report(
		report_name, filters=filters, user=frappe.session.user,
		ignore_prepared_report=True, are_default_filters=True,
	)
	rows = payload.get("result") or []
	# Desk appends a total row after permission filtering; do not count it twice.
	summary_rows = rows[:-1] if rows and payload.get("add_total_row") else rows
	summary = get_report_summary(summary_rows) if report_name == PENDING else payload.get("report_summary")
	return {**payload, "columns": payload.get("columns") or [], "result": rows, "report_summary": summary}


def run_work_order(filters, progress=None):
	return _run(WORK_ORDER, filters)


def run_dispatch(filters, progress=None):
	return _run(DISPATCH, filters, ("lot", "item"))


def run_pending(filters, progress=None):
	return _run(PENDING, filters, tuple(MULTI_FILTERS))
