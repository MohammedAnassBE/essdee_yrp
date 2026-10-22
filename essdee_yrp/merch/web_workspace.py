import frappe
from frappe import _

from essdee_yrp.cutting.reports import get_report_permissions as get_cutting_report_permissions
from essdee_yrp.merch.ipd_workspace import DOCTYPE
from essdee_yrp.merch.reports import can_view_work_in_progress
from essdee_yrp.planning.reports import inward_quantity, size_wise_stock, work_in_progress
from essdee_yrp.planning.reports.desk_adapters import can_run_desk_report
from essdee_yrp.web_common import permission_flags

SECTIONS = {
	"lots": ("Lot", "SD YRP Lot"),
	"item_production_details": ("Item Production Detail", DOCTYPE),
	"production_orders": ("Production Order", "YRP Production Order"),
	"work_orders": ("Work Order", "YRP Work Order"),
	"delivery_challans": ("Delivery Challans", "YRP Delivery Challan"),
	"goods_received_notes": ("Goods Received Notes", "YRP Goods Received Note"),
	"process_costs": ("Process Cost", "YRP Process Cost"),
	"bill_tracking": ("Vendor Bill Tracking", "YRP Bill Tracking"),
	"purchase_invoices": ("Purchase Invoice", "YRP Purchase Invoice"),
}

REPORTS = {
	"work_in_progress": ("Work In Progress", can_view_work_in_progress),
	"inward_quantity": ("Inward Quantity", inward_quantity.can_view),
	"work_order": ("Work Order", lambda: can_run_desk_report("SD YRP Work Order Report")),
	"planning_work_in_progress": ("Work In Progress", work_in_progress.can_view),
	"size_wise_stock": ("Size-wise Stock", size_wise_stock.can_view),
	"multi_ccr": ("Multi CCR", lambda: get_cutting_report_permissions()["multi-ccr"]),
	"ppo_report": ("PPO Report", lambda: frappe.has_permission("YRP Production Order", ptype="report")),
}


@frappe.whitelist()
def get_capabilities() -> dict:
	reports = {key: {"label": _(label), "can_read": bool(access())} for key, (label, access) in REPORTS.items()}
	from essdee_yrp.desk_web_reports import department_report_capabilities

	reports.update(department_report_capabilities("merch", any(report["can_read"] for report in reports.values())))

	return {
		"sections": {
			key: {"label": _(label), **permission_flags(doctype, ("read", "create"))}
			for key, (label, doctype) in SECTIONS.items()
		} | {"reports": {"label": _("Reports"), "can_read": any(report["can_read"] for report in reports.values()), "can_create": False}},
		"reports": reports,
	}
