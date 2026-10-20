"""Desk-backed reports shared by department workspaces."""

import frappe
from frappe import _
from yrp.web_reports.registry import WebReport

GRN_DEPARTMENTS = (
	"cutting", "fabric-store", "cut-panel-store", "accessory-store",
	"sewing", "finishing", "merch", "purchase",
)
STOCK_MOVEMENT_DEPARTMENTS = ("purchase", "accessory-store", "fabric-store", "accounts")
STOCK_MOVEMENT_REPORTS = (
	"jobwork_issued_items", "non_jobwork_issued_items", "non_grn_received_items",
	"lot_wise_stock_ageing", "stock_ageing",
)
DESK_REPORTS = {
	"dc_report": ("DC Report", "SD YRP DC Report"),
	"jobwork_issued_items": ("Jobwork Issued Items", "SD YRP Jobwork Issued Items"),
	"non_jobwork_issued_items": ("Non Jobwork Issued Items", "SD YRP Non Jobwork Issued Items"),
	"non_grn_received_items": ("Non-GRN Received Items", "SD YRP Non-GRN Received Items"),
	"lot_wise_stock_ageing": ("Lot Wise Stock Ageing", "SD YRP Lot Wise Stock Ageing"),
	"stock_ageing": ("YRP Stock Ageing", "YRP Stock Ageing"),
	"grn_report": ("GRN Report", "SD YRP GRN Report"),
	"grn_summary": ("GRN Summary", "SD YRP GRN Summary"),
	"purchase_order_log": ("Purchase Order Log", "SD YRP Purchase Order Log"),
	"lot_purchase_summary": ("Lot Purchase Summary", "SD YRP Lot Purchase Summary"),
	"stock_entry_report": ("Stock Entry Report", "SD YRP Stock Entry Report"),
	"stock_reconciliation_report": ("Stock Reconciliation Report", "SD YRP Stock Reconciliation Report"),
	"stock_update_report": ("Stock Update Report", "SD YRP Stock Update Report"),
	"item_conversion_report": ("Item Conversion Report", "SD YRP Item Conversion Report"),
	"purchase_order_itemwise": ("Purchase Order Itemwise", "SD YRP Purchase Order Itemwise"),
	"lot_consumption_report": ("Lot Consumption Report", "SD YRP Lot Consumption Report"),
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
	if not allowed or department not in (*GRN_DEPARTMENTS, "accounts"):
		return {}
	keys = ["grn_report", "grn_summary", "dc_report", "stock_entry_report", "stock_reconciliation_report", "stock_update_report"] if department in GRN_DEPARTMENTS else []
	if department in STOCK_MOVEMENT_DEPARTMENTS:
		keys.extend(STOCK_MOVEMENT_REPORTS)
	if department in ("purchase", "accessory-store", "fabric-store", "cutting"):
		keys.append("item_conversion_report")
	if department == "purchase":
		keys.extend(("purchase_order_log", "lot_purchase_summary"))
	if department in ("purchase", "accounts"):
		keys.append("purchase_order_itemwise")
	if department in ("purchase", "fabric-store", "accessory-store", "accounts"):
		keys.append("lot_consumption_report")
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
	from yrp.stock.dimensions import get_stock_dimensions
	from yrp.yrp_stock.report.yrp_stock_ageing.yrp_stock_ageing import get_columns as ageing_columns

	from essdee_yrp.essdee_yrp.report.sd_yrp_dc_report.sd_yrp_dc_report import get_columns as dc_columns
	from essdee_yrp.essdee_yrp.report.sd_yrp_grn_report.sd_yrp_grn_report import get_columns as grn_columns
	from essdee_yrp.essdee_yrp.report.sd_yrp_grn_summary.sd_yrp_grn_summary import (
		get_columns as summary_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_item_conversion_report.sd_yrp_item_conversion_report import (
		get_columns as conversion_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_jobwork_issued_items.sd_yrp_jobwork_issued_items import (
		get_columns as jobwork_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_lot_consumption_report.sd_yrp_lot_consumption_report import (
		get_columns as consumption_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_lot_purchase_summary.sd_yrp_lot_purchase_summary import (
		get_columns as lot_purchase_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_lot_wise_stock_ageing.sd_yrp_lot_wise_stock_ageing import (
		get_columns as lot_ageing_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_non_grn_received_items.sd_yrp_non_grn_received_items import (
		get_columns as non_grn_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_non_jobwork_issued_items.sd_yrp_non_jobwork_issued_items import (
		get_columns as non_jobwork_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_purchase_order_itemwise.sd_yrp_purchase_order_itemwise import (
		get_columns as po_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_purchase_order_log.sd_yrp_purchase_order_log import (
		get_columns as log_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_stock_entry_report.sd_yrp_stock_entry_report import (
		get_columns as stock_entry_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_stock_reconciliation_report.sd_yrp_stock_reconciliation_report import (
		get_columns as reconciliation_columns,
	)
	from essdee_yrp.essdee_yrp.report.sd_yrp_stock_update_report.sd_yrp_stock_update_report import (
		get_columns as stock_update_columns,
	)

	ageing_filters = {
		"to_date": "Date", "warehouse": ("Link", "Supplier"), "item": ("Link", "Item"),
		"parent_item": ("Link", "Item"), "range1": "Int", "range2": "Int", "range3": "Int",
		"show_warehouse_wise_stock": "Check",
	}
	ageing_defaults = frappe._dict(range1=30, range2=60, range3=90, show_warehouse_wise_stock=1)
	common_filters = {
		"from_date": "Date", "to_date": "Date", "lot": ("Link", "SD YRP Lot"),
		"supplier": ("Link", "Supplier"), "delivery_location": ("Link", "Supplier"),
	}
	issued_filters = {
		"from_date": "Date", "to_date": "Date", "lot": ("Link", "SD YRP Lot"),
		"from_location": ("Link", "Supplier"), "supplier": ("Link", "Supplier"),
	}
	stock_filters = {
		"from_date": "Date", "to_date": "Date", "item": ("Link", "Item"),
		"item_variant": ("Link", "Item"), "lot": ("Link", "SD YRP Lot"),
	}
	return [
		_desk_entry("purchase-order-itemwise", "SD YRP Purchase Order Itemwise", {
			"item": ("Link", "Item"), "supplier": ("Link", "Supplier"),
			"purchase_order": ("Link", "Purchase Order"), "delivery_location": ("Link", "Supplier"),
			"lot": ("Link", "SD YRP Lot"), "status": "Select", "open_status": "Select",
			"docstatus": "Select", "date_based_on": "Select", "from_date": "Date", "to_date": "Date",
		}, po_columns(), permission_doctypes=("Purchase Order",),
			dependency_doctypes="essdee_yrp.web_reports.purchase_order_dependency_doctypes",
			link_sources={"supplier": "Supplier", "delivery_location": "Supplier"}),
		_desk_entry("lot-consumption-report", "SD YRP Lot Consumption Report", {
			"lot": ("Link", "SD YRP Lot"), "start_date": "Date", "end_date": "Date",
			"item_group": ("Link", "Item Group"),
		}, consumption_columns()),
		_desk_entry("dc-report", "SD YRP DC Report", issued_filters, dc_columns()),
		_desk_entry("jobwork-issued-items", "SD YRP Jobwork Issued Items", {
			**issued_filters, "item": ("Link", "Item"),
		}, jobwork_columns()),
		_desk_entry("non-jobwork-issued-items", "SD YRP Non Jobwork Issued Items", {
			**issued_filters, "purpose": "Select", "item": ("Link", "Item"),
		}, non_jobwork_columns()),
		_desk_entry("non-grn-received-items", "SD YRP Non-GRN Received Items", {
			"from_date": "Date", "to_date": "Date", "lot": ("Link", "SD YRP Lot"),
			"supplier": ("Link", "Supplier"), "purpose": "Select", "item": ("Link", "Item"),
			"received_location": ("Link", "Supplier"),
		}, non_grn_columns()),
		_desk_entry("lot-wise-stock-ageing", "SD YRP Lot Wise Stock Ageing", {
			**ageing_filters, "lot": ("Link", "SD YRP Lot"), "brand": ("Link", "Brand"),
		}, lot_ageing_columns(ageing_defaults)),
		_desk_entry("stock-ageing", "YRP Stock Ageing", ageing_filters,
			ageing_columns(ageing_defaults, get_stock_dimensions())),
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
		_desk_entry("stock-entry-report", "SD YRP Stock Entry Report", {
			**stock_filters, "from_warehouse": ("Link", "Supplier"), "to_warehouse": ("Link", "Supplier"),
		}, stock_entry_columns()),
		_desk_entry("stock-reconciliation-report", "SD YRP Stock Reconciliation Report", {
			**stock_filters, "supplier": ("Link", "Supplier"),
		}, reconciliation_columns()),
		_desk_entry("stock-update-report", "SD YRP Stock Update Report", {
			**stock_filters, "warehouse": ("Link", "Supplier"),
		}, stock_update_columns()),
		_desk_entry("item-conversion-report", "SD YRP Item Conversion Report", {
			"from_date": "Date", "to_date": "Date", "lot": ("Link", "SD YRP Lot"),
			"from_item": ("Link", "Item"), "to_item": ("Link", "Item"),
		}, conversion_columns()),
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


def _desk_entry(key, name, filters, columns, *, permission_doctypes=(), dependency_doctypes=None, link_sources=None):
	return WebReport(
		key=key, kind="frappe_report", report=name, filters=filters,
		base_columns={column["fieldname"]: column["label"] for column in columns},
		link_sources={**{column["fieldname"]: column["options"] for column in columns if column.get("fieldtype") == "Link"}, **(link_sources or {})},
		permission_doctypes=permission_doctypes, dependency_doctypes=dependency_doctypes,
		background="never",
	)
