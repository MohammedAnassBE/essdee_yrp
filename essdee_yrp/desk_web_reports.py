"""Desk-backed reports shared by department workspaces."""

import frappe
from frappe import _
from yrp.web_reports.registry import WebReport

GRN_DEPARTMENTS = (
	"cutting", "fabric-store", "cut-panel-store", "accessory-store",
	"sewing", "finishing", "merch", "purchase",
)
DESK_REPORTS = {
	"grn_report": ("GRN Report", "SD YRP GRN Report"),
	"grn_summary": ("GRN Summary", "SD YRP GRN Summary"),
	"purchase_order_log": ("Purchase Order Log", "SD YRP Purchase Order Log"),
	"lot_purchase_summary": ("Lot Purchase Summary", "SD YRP Lot Purchase Summary"),
}
FI_COLUMNS = [
	{"fieldname": "lot", "label": "Lot", "fieldtype": "Link", "options": "SD YRP Lot", "width": 160},
	{"fieldname": "item", "label": "Item", "fieldtype": "Link", "options": "Item", "width": 180},
	{"fieldname": "colour", "label": "Colour", "fieldtype": "Data", "width": 140},
	{"fieldname": "part", "label": "Part", "fieldtype": "Data", "width": 140},
	{"fieldname": "sewing_plan", "label": "Sewing Plan", "fieldtype": "Link", "options": "SD YRP Sewing Plan", "width": 180},
]


def can_run_desk_report(name):
	from essdee_yrp.fabric_store.web_workspace import can_run_report

	return can_run_report(name)


def can_view_fi_updates():
	roles = frappe.get_roles()
	planner_role = frappe.db.get_single_value("SD YRP MRP Settings", "production_planner_role")
	return bool(
		("System Manager" in roles or (planner_role and planner_role in roles))
		and frappe.has_permission("SD YRP Sewing Plan", ptype="read")
		and frappe.has_permission("SD YRP Sewing Plan", ptype="report")
	)


def department_report_capabilities(department, allowed):
	"""Keep additions inside the department's existing report access."""
	if not allowed or department not in GRN_DEPARTMENTS:
		return {}
	keys = ["grn_report", "grn_summary"]
	if department == "purchase":
		keys.extend(("purchase_order_log", "lot_purchase_summary"))
	reports = {
		key: {"label": _(DESK_REPORTS[key][0]), "can_read": True, "can_report": True}
		for key in keys if can_run_desk_report(DESK_REPORTS[key][1])
	}
	if department == "sewing" and can_view_fi_updates():
		reports["finishing_inward_updates"] = {
			"label": _("Finishing Inward Updates"), "can_read": True, "can_report": True,
		}
	return reports


def require_fi_updates_access():
	if not can_view_fi_updates():
		frappe.throw(_("You do not have permission to view Finishing Inward Updates."), frappe.PermissionError)


def run_fi_updates(filters):
	from essdee_yrp.sewing.read_models import get_fi_updates_data

	require_fi_updates_access()
	if not filters.get("supplier"):
		frappe.throw(_("Select a Sewing Unit."))
	return {"columns": FI_COLUMNS, "result": get_fi_updates_data(filters["supplier"])["data"]}


def get_reports():
	from essdee_yrp.essdee_yrp.report.sd_yrp_grn_report.sd_yrp_grn_report import get_columns as grn_columns
	from essdee_yrp.essdee_yrp.report.sd_yrp_grn_summary.sd_yrp_grn_summary import get_columns as summary_columns
	from essdee_yrp.essdee_yrp.report.sd_yrp_purchase_order_log.sd_yrp_purchase_order_log import get_columns as log_columns
	from essdee_yrp.essdee_yrp.report.sd_yrp_lot_purchase_summary.sd_yrp_lot_purchase_summary import get_columns as lot_purchase_columns

	common_filters = {
		"from_date": "Date", "to_date": "Date", "lot": ("Link", "SD YRP Lot"),
		"supplier": ("Link", "Supplier"), "delivery_location": ("Link", "Supplier"),
	}
	return [
		_desk_entry("grn-report", "SD YRP GRN Report", common_filters, grn_columns()),
		_desk_entry("grn-summary", "SD YRP GRN Summary", {
			**common_filters, "item": ("Link", "Item"), "only_show_stock_item": "Check", "status": "Select",
		}, summary_columns()),
		_desk_entry("purchase-order-log", "SD YRP Purchase Order Log", {
			"purchase_order": ("Link", "Purchase Order"), "po_date": "Date", "supplier": ("Link", "Supplier"),
		}, log_columns()),
		_desk_entry("lot-purchase-summary", "SD YRP Lot Purchase Summary", {
			"lot": ("Link", "SD YRP Lot"), "item": ("Link", "Item"), "parent_item": ("Link", "Item"),
		}, lot_purchase_columns()),
		WebReport(
			key="finishing-inward-updates", kind="callable",
			runner="essdee_yrp.desk_web_reports.run_fi_updates",
			access="essdee_yrp.desk_web_reports.require_fi_updates_access",
			filters={"supplier": ("Link", "Supplier")},
			base_columns={column["fieldname"]: column["label"] for column in FI_COLUMNS},
			link_sources={"lot": "SD YRP Lot", "item": "Item", "sewing_plan": "SD YRP Sewing Plan"},
			permission_doctypes=("SD YRP Sewing Plan",), background="never",
		),
	]


def _desk_entry(key, name, filters, columns):
	return WebReport(
		key=key, kind="frappe_report", report=name, filters=filters,
		base_columns={column["fieldname"]: column["label"] for column in columns},
		link_sources={column["fieldname"]: column["options"] for column in columns if column.get("fieldtype") == "Link"},
		background="never",
	)
