import frappe
from yrp.web_reports.registry import WebReport

from essdee_yrp.cut_panel_store.report_workspace import CUT_BUNDLE_COLUMNS
from essdee_yrp.essdee_yrp.report.sd_yrp_dispatch_percentage_report.sd_yrp_dispatch_percentage_report import (
	get_columns as get_dispatch_percentage_columns,
)
from essdee_yrp.essdee_yrp.report.sd_yrp_finishing_plan_report.sd_yrp_finishing_plan_report import (
	get_columns as get_finishing_plan_columns,
)
from essdee_yrp.essdee_yrp.report.sd_yrp_work_order_pending_report.sd_yrp_work_order_pending_report import (
	get_columns as get_work_order_pending_columns,
)
from essdee_yrp.essdee_yrp.report.sd_yrp_work_order_report.sd_yrp_work_order_report import (
	get_columns as get_work_order_columns,
)


def get_reports() -> list[WebReport]:
	return [
		WebReport(
			key="merch-work-in-progress", kind="callable",
			runner="essdee_yrp.merch.reports.run_work_in_progress",
			access="essdee_yrp.merch.reports.require_work_in_progress_access",
			filters={"category": ("Link", "SD YRP Product Category"), "product_season": ("Link", "SD YRP Product Season"),
				"lot_status": "Select", "lot": "JSON", "item": "JSON", "from_date": "Date", "to_date": "Date", "process_list": "JSON"},
			link_sources={"lot": "SD YRP Lot", "item": "Item", "production_order": "YRP Production Order"},
			permission_doctypes=("SD YRP Lot", "YRP Work Order"),
			dependency_doctypes="essdee_yrp.merch.reports.work_in_progress_dependency_doctypes", background="never",
		),
		WebReport(
			key="planning-colour-wise-diff", kind="callable",
			runner="essdee_yrp.planning.reports.colour_wise_diff.run",
			access="essdee_yrp.planning.reports.colour_wise_diff.require_access",
			filters={"lot": ("Link", "SD YRP Lot"), "process_list": "JSON"},
			permission_doctypes=("SD YRP Lot", "YRP Work Order", "YRP Item Production Detail"),
			dependency_doctypes="essdee_yrp.planning.reports.colour_wise_diff.dependency_doctypes", background="never",
		),
		WebReport(
			key="planning-size-wise-stock", kind="callable",
			runner="essdee_yrp.planning.reports.size_wise_stock.run",
			access="essdee_yrp.planning.reports.size_wise_stock.require_access",
			filters={"lot": "JSON", "item": "JSON", "product_category": ("Link", "SD YRP Product Category"), "lot_status": "Select", "process_list": "JSON"},
			permission_doctypes=("SD YRP Lot", "YRP Work Order", "YRP Item Production Detail", "SD YRP Finishing Plan"),
			dependency_doctypes="essdee_yrp.planning.reports.size_wise_stock.dependency_doctypes", background="never",
		),
		WebReport(
			key="planning-work-in-progress", kind="callable",
			runner="essdee_yrp.planning.reports.work_in_progress.run",
			access="essdee_yrp.planning.reports.work_in_progress.require_access",
			filters={"lot": "JSON", "item": "JSON", "category": ("Link", "SD YRP Product Category"), "lot_status": "Select", "process_list": "JSON", "from_date": "Date", "to_date": "Date"},
			link_sources={"lot": "SD YRP Lot", "item": "Item"},
			permission_doctypes=("SD YRP Lot", "YRP Work Order", "YRP Item Production Detail", "SD YRP Finishing Plan", "SD YRP GRN Rework Item", "YRP Goods Received Note"),
			dependency_doctypes="essdee_yrp.planning.reports.work_in_progress.dependency_doctypes",
			background={"days": 31, "from_field": "from_date", "to_field": "to_date", "missing_bound": "background"},
		),
		WebReport(
			key="planning-inward-quantity", kind="callable",
			runner="essdee_yrp.planning.reports.inward_quantity.run",
			access="essdee_yrp.planning.reports.inward_quantity.require_access",
			filters={"lot": ("Link", "SD YRP Lot"), "process": ("Link", "YRP Process")},
			permission_doctypes=("YRP Work Order", "SD YRP Lot"),
			dependency_doctypes="essdee_yrp.planning.reports.inward_quantity.dependency_doctypes", background="never",
		),
		WebReport(
			key="planning-inhouse-quantity", kind="callable",
			runner="essdee_yrp.planning.reports.inhouse_quantity.run",
			access="essdee_yrp.planning.reports.inhouse_quantity.require_access",
			filters={"lot": ("Link", "SD YRP Lot"), "process": ("Link", "YRP Process")},
			permission_doctypes=("YRP Work Order", "SD YRP Lot"),
			dependency_doctypes="essdee_yrp.planning.reports.inhouse_quantity.dependency_doctypes", background="never",
		),
		WebReport(
			key="planning-month-wise-detail", kind="callable",
			runner="essdee_yrp.planning.reports.month_wise_detail.run",
			access="essdee_yrp.planning.reports.month_wise_detail.require_access",
			filters={"lot": "JSON", "item": "JSON", "from_date": "Date", "to_date": "Date"},
			permission_doctypes=("YRP Work Order", "SD YRP Lot", "YRP Stock Entry", "SD YRP Finishing Plan"),
			dependency_doctypes="essdee_yrp.planning.reports.month_wise_detail.dependency_doctypes", background="never",
		),
		WebReport(
			key="planning-process-pending", kind="callable",
			runner="essdee_yrp.planning.reports.process_pending.run",
			access="essdee_yrp.planning.reports.process_pending.require_access",
			filters={"lot": "JSON", "item": "JSON", "category": ("Link", "SD YRP Product Category"), "lot_status": "Select", "process": ("Link", "YRP Process")},
			link_sources={"lot": "SD YRP Lot", "item": "Item"},
			permission_doctypes=("YRP Work Order", "SD YRP Lot"),
			dependency_doctypes="essdee_yrp.planning.reports.process_pending.dependency_doctypes", background="never",
		),
		WebReport(
			key="planning-work-order", kind="callable", report="SD YRP Work Order Report",
			runner="essdee_yrp.planning.reports.desk_adapters.run_work_order",
			access="essdee_yrp.planning.reports.desk_adapters.require_work_order_access",
			filters={
				"based_on": "Select", "from_date": "Date", "to_date": "Date",
				"supplier": ("Link", "Supplier"), "process_name": ("Link", "YRP Process"),
				"item": ("Link", "Item"), "lot": ("Link", "SD YRP Lot"), "status": "Select",
			},
			link_sources={"work_order": "YRP Work Order", "supplier": "Supplier", "lot": "SD YRP Lot", "item": "Item"},
			base_columns=_column_labels(get_work_order_columns(
				(frappe.db.get_single_value("SD YRP MRP Settings", "received_type_list") or "").split(",")
			)),
			permission_doctypes=("YRP Work Order",),
			dependency_doctypes="essdee_yrp.web_reports.planning_work_order_dependency_doctypes",
			background="never",
		),
		WebReport(
			key="planning-dispatch-percentage", kind="callable", report="SD YRP Dispatch Percentage Report",
			runner="essdee_yrp.planning.reports.desk_adapters.run_dispatch",
			access="essdee_yrp.planning.reports.desk_adapters.require_dispatch_access",
			filters={"percentage": "Percent", "lot": "JSON", "item": "JSON"},
			link_sources={"lot": "SD YRP Lot", "item": "Item", "stock_entry": "YRP Stock Entry"},
			base_columns=_column_labels(get_dispatch_percentage_columns()),
			permission_doctypes=("SD YRP Finishing Plan",),
			dependency_doctypes="essdee_yrp.web_reports.planning_dispatch_dependency_doctypes",
			background="never",
		),
		WebReport(
			key="planning-work-order-pending", kind="callable", report="SD YRP Work Order Pending Report",
			runner="essdee_yrp.planning.reports.desk_adapters.run_pending",
			access="essdee_yrp.planning.reports.desk_adapters.require_pending_access",
			filters={
				"production_order": "JSON", "lot": "JSON", "item": "JSON", "item_variant": "JSON",
				"process": "JSON", "supplier": "JSON", "from_date": "Date", "to_date": "Date", "status": "Select",
			},
			link_sources={"production_order": "YRP Production Order", "work_order": "YRP Work Order", "lot": "SD YRP Lot", "item_variant": "Item", "process_name": "YRP Process"},
			base_columns=_column_labels(get_work_order_pending_columns()),
			permission_doctypes=("YRP Work Order",),
			dependency_doctypes="essdee_yrp.web_reports.planning_work_order_dependency_doctypes",
			background="never",
		),
		WebReport(
			key="finishing-plan",
			kind="frappe_report",
			report="SD YRP Finishing Plan Report",
			filters={
				"lot": ("Link", "SD YRP Lot"),
				"item": ("Link", "Item"),
				"season": ("Link", "SD YRP Product Season"),
				"product_category": ("Link", "SD YRP Product Category"),
			},
			link_sources={"item": "Item", "lot": "SD YRP Lot"},
			base_columns=_column_labels(get_finishing_plan_columns()),
			permission_doctypes=("SD YRP Finishing Plan",),
			dependency_doctypes="essdee_yrp.web_reports.finishing_plan_dependency_doctypes",
			background="never",
		),
		WebReport(
			key="cut-bundle-balance",
			kind="callable",
			runner="essdee_yrp.cut_panel_store.report_workspace.get_cut_bundle_result",
			access="essdee_yrp.cut_panel_store.report_workspace.require_cut_bundle_report_access",
			filters={"lot": ("Link", "SD YRP Lot"), "supplier": ("Link", "Supplier")},
			link_sources={"lot": "SD YRP Lot", "supplier": "Supplier", "item": "Item"},
			base_columns=_column_labels(CUT_BUNDLE_COLUMNS),
			permission_doctypes=("SD YRP Cut Bundle Movement Ledger",),
			dependency_doctypes="essdee_yrp.web_reports.cut_bundle_dependency_doctypes",
			background="never",
		),
		WebReport(
			key="cutting-dpr",
			kind="callable",
			runner="essdee_yrp.cutting.reports.run_cutting_dpr",
			access="essdee_yrp.cutting.reports.require_cutting_report_access",
			filters={
				"mode": "Select",
				"date": "Date",
				"items": "JSON",
				"lots": "JSON",
				"location": "Data",
				"from_date": "Date",
				"to_date": "Date",
			},
			permission_doctypes=("SD YRP Cutting LaySheet",),
			dependency_doctypes="essdee_yrp.cutting.reports.cutting_dpr_dependency_doctypes",
			background={
				"days": 10,
				"from_field": "from_date",
				"to_field": "to_date",
				"when": {"mode": "summary"},
				"missing_bound": "background",
			},
		),
	]


def purchase_order_dependency_doctypes(filters=None) -> list[str]:
	return ["Item", "Purchase Order", "Purchase Order Item", "SD YRP Lot", "Supplier", "UOM", "User"]


def finishing_plan_dependency_doctypes(filters=None) -> list[str]:
	return [
		"Item",
		"SD YRP Finishing Plan",
		"SD YRP Lot",
		"SD YRP Product Category",
		"SD YRP Product Season",
		"YRP Item Production Detail",
	]


def cut_bundle_dependency_doctypes(filters=None) -> list[str]:
	return ["Item", "SD YRP Cut Bundle Movement Ledger", "SD YRP Lot", "Supplier"]


def _column_labels(columns) -> dict[str, str]:
	return {column["fieldname"]: column.get("label") or column["fieldname"] for column in columns}


def planning_work_order_dependency_doctypes(filters=None) -> list[str]:
	return ["YRP Work Order", "YRP Work Order Calculated Item", "YRP Work Order Deliverables", "YRP Work Order Receivables", "SD YRP MRP Settings", "YRP Production Order", "SD YRP Lot", "Item", "Supplier", "YRP Process", "YRP Item Production Detail", "YRP Goods Received Note", "YRP Goods Received Note Item"]


def planning_dispatch_dependency_doctypes(filters=None) -> list[str]:
	return ["SD YRP Finishing Plan", "SD YRP Finishing Plan Dispatch Log", "SD YRP Lot", "Item", "YRP Stock Entry"]
