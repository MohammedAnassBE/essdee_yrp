import frappe
from frappe import _

from essdee_yrp.accounts import audit_pending
from essdee_yrp.cutting.reports import get_report_permissions
from essdee_yrp.fabric_store.web_workspace import can_run_report
from essdee_yrp.finishing.web_reports import can_view_dispatch_report
from essdee_yrp.finishing.web_workspace import get_capabilities as get_finishing_capabilities
from essdee_yrp.sewing.web_workspace import get_capabilities as get_sewing_capabilities

ACCOUNTS_REPORT_ROLES = frozenset({"Accounts User", "Accounts Manager", "System Manager"})


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
def get_capabilities() -> dict:
	reports = {}
	if can_view_accounts_reports():
		reports = {
			key: {"label": _(label), "can_read": True}
			for key, (label, is_allowed) in REPORT_GATES.items()
			if is_allowed()
		}
	return {
		"sections": {
			"purchase_invoices": {
				"label": _("Purchase Invoice"),
				"can_read": bool(frappe.has_permission("YRP Purchase Invoice", ptype="read")),
				"can_create": bool(frappe.has_permission("YRP Purchase Invoice", ptype="create")),
			},
			"reports": {"label": _("Reports"), "can_read": bool(reports)},
		},
		"reports": reports,
	}
