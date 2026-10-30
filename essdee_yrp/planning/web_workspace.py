import frappe
from frappe import _

from essdee_yrp.cutting import reports as cutting_reports
from essdee_yrp.cutting import web_capabilities as cutting_capabilities
from essdee_yrp.fabric_store import web_workspace as fabric_store_workspace
from essdee_yrp.finishing import web_workspace as finishing_workspace
from essdee_yrp.planning.reports import (
	colour_wise_diff,
	inhouse_quantity,
	inward_quantity,
	month_wise_detail,
	process_pending,
	size_wise_stock,
	work_in_progress,
)
from essdee_yrp.planning.reports.desk_adapters import can_run_desk_report
from essdee_yrp.sales import web_workspace as sales_workspace
from essdee_yrp.sewing import web_workspace as sewing_workspace
from essdee_yrp.web_common import permission_flags, report_access_scope


def _with_label(label, flags):
	return {"label": _(label), **(flags or {})}


def _reports_section(sewing_sections, finishing_sections):
	production = {
		key: {"label": _(label), "can_read": True}
		for key, label, report in (
			("work_order", "Work Order", "SD YRP Work Order Report"),
			("dispatch_percentage", "Dispatch Percentage", "SD YRP Dispatch Percentage Report"),
			("work_order_pending", "Work Order Pending", "SD YRP Work Order Pending Report"),
		)
		if can_run_desk_report(report)
	}
	if finishing_sections.get("reports", {}).get("reports", {}).get("finishing_plan_report", {}).get("can_read"):
		production["finishing_plan"] = {"label": _("Finishing Plan Report"), "can_read": True}
	for key, label, report in (
		("inward_quantity", "Inward Quantity", inward_quantity),
		("inhouse_quantity", "In-house Quantity", inhouse_quantity),
		("month_wise_detail", "Month-wise Detail", month_wise_detail),
		("process_pending", "Process Pending", process_pending),
		("size_wise_stock", "Size-wise Stock", size_wise_stock),
		("colour_wise_diff", "Colour-wise Diff", colour_wise_diff),
		("work_in_progress", "Work In Progress", work_in_progress),
	):
		if report.can_view():
			production[key] = {"label": _(label), "can_read": True}
	if cutting_reports.get_report_permissions()["multi-ccr"]:
		production["multi_ccr"] = {"label": _("Multi CCR"), "can_read": True}
	if frappe.has_permission("YRP Production Order", "report"):
		production["ppo_report"] = {"label": _("PPO Report"), "can_read": True, "can_export": True}
	if frappe.has_permission("YRP Work Order", "read"):
		production["work_order_bulk_close"] = {
			"label": _("Work Order Bulk Close"), "can_read": True,
			"can_write": bool(frappe.has_permission("YRP Work Order", "write")),
		}
	groups = {
		"cutting": any(
			value for key, value in cutting_reports.get_report_permissions().items()
			if key != "cutting-plans"
		),
		"sewing": bool(sewing_sections.get("reports")),
		"finishing": bool(finishing_sections.get("reports")),
		"production": bool(production),
	}
	return {"label": _("Reports"), "can_read": any(groups.values()), "groups": groups, "production": production}


@frappe.whitelist()
@report_access_scope()
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
		"delivery_challans": fabric_store_sections.get("delivery_challans") or {},
		"goods_received_notes": fabric_store_sections.get("goods_received_notes") or {},
		"dispatches": finishing_sections.get("dispatches") or {},
		"rework_details": finishing_sections.get("rework_details") or {},
		"purchase_orders": fabric_store_sections.get("purchase_orders") or {},
		"stock_transfers": {"can_read": True, **fabric_store_sections["stock_transfers"]}
		if "stock_transfers" in fabric_store_sections else {},
		"box_stickers": _with_label(
			"Box Sticker Print",
			permission_flags("SD YRP Box Sticker Print", ("read", "create", "write", "submit")),
		),
		"reports": _reports_section(sewing_sections, finishing_sections),
	}
	return {"sections": {key: flags for key, flags in sections.items() if flags.get("can_read")}}
