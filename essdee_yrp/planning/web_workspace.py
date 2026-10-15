import frappe
from frappe import _

from essdee_yrp.cutting import reports as cutting_reports
from essdee_yrp.cutting import web_capabilities as cutting_capabilities
from essdee_yrp.fabric_store import web_workspace as fabric_store_workspace
from essdee_yrp.finishing import web_workspace as finishing_workspace
from essdee_yrp.sales import web_workspace as sales_workspace
from essdee_yrp.sewing import web_workspace as sewing_workspace
from essdee_yrp.web_common import permission_flags


def _with_label(label, flags):
	return {"label": _(label), **(flags or {})}


def _reports_section(sewing_sections, finishing_sections):
	groups = {
		"cutting": any(
			value for key, value in cutting_reports.get_report_permissions().items()
			if key != "cutting-plans"
		),
		"sewing": bool(sewing_sections.get("reports")),
		"finishing": bool(finishing_sections.get("reports")),
	}
	return {"label": _("Reports"), "can_read": any(groups.values()), "groups": groups}


@frappe.whitelist()
def get_capabilities() -> dict:
	sewing_sections = sewing_workspace.get_capabilities()["sections"]
	finishing_sections = finishing_workspace.get_capabilities()["sections"]
	sales_sections = sales_workspace.get_capabilities()["sections"]
	fabric_store_sections = fabric_store_workspace.get_capabilities()["sections"]
	sections = {
		"cutting_plans": _with_label(
			"Cutting Plan", cutting_capabilities.get_capabilities().get("cutting-plans")
		),
		"sewing_plans": _with_label("Sewing Plan", sewing_sections.get("plans")),
		"finishing_plans": _with_label("Finishing Plan", finishing_sections.get("plans")),
		"lots": _with_label("Lot", permission_flags("SD YRP Lot", ("read", "write"))),
		"production_orders": sales_sections.get("production_orders") or {},
		"work_orders": fabric_store_sections.get("work_orders") or {},
		"reports": _reports_section(sewing_sections, finishing_sections),
	}
	return {"sections": {key: flags for key, flags in sections.items() if flags.get("can_read")}}
