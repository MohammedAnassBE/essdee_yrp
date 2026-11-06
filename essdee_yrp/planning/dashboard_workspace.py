import frappe
from frappe import _

from essdee_yrp.planning.dashboard import dashboard, process_detail, tracking
from essdee_yrp.planning.reports.production_quantities import can_read

DASHBOARD_DOCTYPES = ("SD YRP Lot", "YRP Production Order", "YRP Work Order", "SD YRP Finishing Plan")


def has_dashboard_access():
	return can_read(*DASHBOARD_DOCTYPES)


def require_dashboard_access():
	if not has_dashboard_access():
		frappe.throw(_("You do not have access to the Planning Dashboard."), frappe.PermissionError)


@frappe.whitelist()
def get_dashboard() -> dict:
	require_dashboard_access()
	return dashboard.get_dashboard_data()


@frappe.whitelist()
def get_tracking_options() -> dict:
	require_dashboard_access()
	return tracking.get_tracking_options()


@frappe.whitelist()
def get_tracking(ppos=None, lots=None) -> dict:
	require_dashboard_access()
	return tracking.get_tracking_data(ppos, lots)


@frappe.whitelist()
def get_process_detail(lot: str, process: str) -> dict:
	require_dashboard_access()
	return process_detail.get_process_detail(lot, process)
