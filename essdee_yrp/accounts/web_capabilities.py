import frappe
from frappe import _

from essdee_yrp.accounts import audit_pending
from essdee_yrp.cutting.reports import get_report_permissions
from essdee_yrp.desk_web_reports import department_report_capabilities
from essdee_yrp.fabric_store.web_workspace import can_run_report
from essdee_yrp.finishing.web_reports import can_view_dispatch_report
from essdee_yrp.finishing.web_workspace import get_capabilities as get_finishing_capabilities
from essdee_yrp.sewing.web_workspace import get_capabilities as get_sewing_capabilities
from essdee_yrp.web_common import report_access_scope

ACCOUNTS_REPORT_ROLES = frozenset({"Accounts User", "Accounts Manager", "System Manager"})
# Read-only cards that open the Merch Lot and PD Lotwise Item Profit pages.
COMBINED_SECTIONS = {
	"lots": ("Lot", "SD YRP Lot"),
	"lotwise_item_profits": ("Lotwise Item Profit", "SD YRP Lotwise Item Profit"),
}


def can_view_accounts_reports():
	return bool(ACCOUNTS_REPORT_ROLES.intersection(frappe.get_roles()))


def _sewing_report_allowed(key):
	report = get_sewing_capabilities()["reports"].get(key, {})
	return bool(report.get("can_read") and report.get("can_report"))


def _finishing_report_allowed(key):
	reports = get_finishing_capabilities()["sections"].get("reports", {}).get("reports", {})
	return bool(reports.get(key, {}).get("can_read"))


REPORT_GATES = {
	"stock_balance": ("Stock Balance", lambda: can_run_report("YRP Stock Balance")),
	"cutting_dpr": (
		"Cutting DPR",
		lambda: bool(get_report_permissions().get("daily-production")),
	),
	"sewing_dpr": ("Sewing DPR", lambda: _sewing_report_allowed("dpr")),
	"finishing_dispatch": ("Finishing Dispatch", can_view_dispatch_report),
	"ironing_dpr": ("Ironing DPR", lambda: _finishing_report_allowed("ironing_dpr")),
	"audit_pending_finishing_plans": ("Audit Pending Finishing Plans", audit_pending.can_view),
}


@frappe.whitelist()
@report_access_scope()
def get_capabilities() -> dict:
	reports = {}
	if can_view_accounts_reports():
		reports = {
			key: {"label": _(label), "can_read": True}
			for key, (label, is_allowed) in REPORT_GATES.items()
			if is_allowed()
		}
		reports.update(department_report_capabilities("accounts", True))
	return {
		"sections": {
			"debits": {"label": _("Debits"), "can_read": bool(frappe.has_permission("YRP Debit", ptype="read"))},
			"purchase_invoices": {
				"label": _("Purchase Invoice"),
				"can_read": bool(frappe.has_permission("YRP Purchase Invoice", ptype="read")),
				"can_create": bool(frappe.has_permission("YRP Purchase Invoice", ptype="create")),
			},
			"bill_tracking": {
				"label": _("Bill Tracking"),
				"can_read": bool(frappe.has_permission("YRP Bill Tracking", ptype="read")),
				"can_create": bool(frappe.has_permission("YRP Bill Tracking", ptype="create")),
			},
			**{
				key: {"label": _(label), "can_read": bool(frappe.has_permission(doctype, ptype="read")), "can_create": False}
				for key, (label, doctype) in COMBINED_SECTIONS.items()
			},
			"reports": {"label": _("Reports"), "can_read": bool(reports)},
		},
		"reports": reports,
	}
