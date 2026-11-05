import frappe

from essdee_yrp.essdee_yrp.report.sd_yrp_supplier_pending_report import (
	sd_yrp_supplier_pending_report as desk_report,
)
from essdee_yrp.planning.reports import production_quantities as quantities


def can_view() -> bool:
	return frappe.session.user != "Guest" and bool(frappe.has_permission("YRP Work Order", "report"))


def require_access() -> None:
	quantities.require_report_access(can_view())


@frappe.whitelist()
def get_supplier_pending_report(supplier, process):
	"""Pending quantities of one supplier and process, grouped by item, lot, colour and size."""
	require_access()
	return desk_report.get_supplier_pending_report(supplier, process)
