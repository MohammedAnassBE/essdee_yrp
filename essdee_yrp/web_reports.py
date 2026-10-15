from yrp.web_reports.registry import WebReport

from essdee_yrp.cut_panel_store.report_workspace import CUT_BUNDLE_COLUMNS
from essdee_yrp.essdee_yrp.report.sd_yrp_finishing_plan_report.sd_yrp_finishing_plan_report import (
	get_columns as get_finishing_plan_columns,
)
from essdee_yrp.essdee_yrp.report.sd_yrp_purchase_order_itemwise.sd_yrp_purchase_order_itemwise import (
	get_columns as get_purchase_order_columns,
)


def get_reports() -> list[WebReport]:
	return [
		WebReport(
			key="accounts-audit-pending-finishing-plans",
			kind="callable",
			runner="essdee_yrp.accounts.audit_pending.run",
			access="essdee_yrp.accounts.audit_pending.require_access",
			filters={
				"lot": ("Link", "SD YRP Lot"),
				"item": ("Link", "Item"),
				"from_date": "Date",
				"to_date": "Date",
			},
			link_sources={
				"name": "SD YRP Finishing Plan", "lot": "SD YRP Lot",
				"item": "Item", "work_order": "YRP Work Order",
			},
			permission_doctypes=("SD YRP Finishing Plan",),
			dependency_doctypes="essdee_yrp.accounts.audit_pending.dependency_doctypes",
			background="never",
		),
		WebReport(
			key="purchase-order-itemwise",
			kind="frappe_report",
			report="SD YRP Purchase Order Itemwise",
			filters={
				"item": ("Link", "Item"),
				"item_variant": ("Link", "Item"),
				"supplier": ("Link", "Supplier"),
				"purchase_order": ("Link", "Purchase Order"),
				"delivery_location": ("Link", "Supplier"),
				"lot": ("Link", "SD YRP Lot"),
				"status": "Select",
				"open_status": "Select",
				"docstatus": "Select",
				"date_based_on": "Select",
				"from_date": "Date",
				"to_date": "Date",
			},
			link_sources={
				"name": "Purchase Order",
				"supplier": "Supplier",
				"item": "Item",
				"item_variant": "Item",
				"uom": "UOM",
				"lot": "SD YRP Lot",
				"modified_by": "User",
			},
			base_columns=_column_labels(get_purchase_order_columns()),
			permission_doctypes=("Purchase Order",),
			dependency_doctypes="essdee_yrp.web_reports.purchase_order_dependency_doctypes",
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
