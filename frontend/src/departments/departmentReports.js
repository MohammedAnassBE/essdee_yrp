import { combinedDeskReports, departmentDeskReports } from "../components/reports/deskReportConfig.js"

const lotCutQuantityProps = (report) => ({ canReadCuttingPlan: Boolean(report?.can_read_cutting_plan) })
const readable = (definitions, reports) => definitions.filter((report) => reports?.[report.key]?.can_read)
	.map((report) => ({ ...report, props: { ...report.props, ...report.capabilityProps?.(reports[report.key]) } }))

export const CUTTING_REPORTS = [
	{ value: "daily-production", label: "Daily Production", icon: "pi pi-chart-line" },
	{ value: "daily-cut-sheet", label: "Daily Cut Sheet", icon: "pi pi-table" },
	{ value: "multi-ccr", label: "Multi CCR", icon: "pi pi-chart-scatter" },
	{ value: "cutting-detail", label: "Cutting Detail", icon: "pi pi-chart-bar" },
	{ value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse" },
]

/** Cutting permissions are a `{ "report-value": true }` map. */
export function cuttingReportTabs(permissions = {}) {
	const capabilities = Object.fromEntries(Object.entries(permissions).map(([key, can_read]) => [key.replaceAll("-", "_"), { can_read }]))
	return [...CUTTING_REPORTS.filter((report) => permissions[report.value]), ...departmentDeskReports("cutting", capabilities)]
}

export const MERCH_REPORTS = [
	{ key: "work_in_progress", value: "work-in-progress", label: "Work In Progress", icon: "pi pi-chart-bar" },
	{ key: "inward_quantity", value: "inward-quantity", label: "Inward Quantity", icon: "pi pi-sign-in" },
	{ key: "work_order", value: "work-order", label: "Work Order", icon: "pi pi-briefcase" },
	{ key: "planning_work_in_progress", value: "planning-work-in-progress", label: "Work In Progress", icon: "pi pi-chart-line" },
	{ key: "size_wise_stock", value: "size-wise-stock", label: "Size-wise Stock", icon: "pi pi-th-large" },
	{ key: "multi_ccr", value: "multi-ccr", label: "Multi CCR", icon: "pi pi-chart-scatter" },
	{ key: "ppo_report", value: "ppo-report", label: "PPO Report", icon: "pi pi-file", props: { canExport: true } },
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse" },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", capabilityProps: lotCutQuantityProps },
]
const MERCH_DESK_DEPARTMENTS = { merch: ["merch"], "merch-purchase": ["merch", "purchase"] }

export function merchReportTabs(department, reports = {}) {
	return [...readable(MERCH_REPORTS, reports), ...combinedDeskReports(MERCH_DESK_DEPARTMENTS[department] || [], reports)]
}

export const FINISHING_REPORTS = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse" },
	{ key: "packing_dpr", value: "packing-dpr", label: "Packing DPR", icon: "pi pi-box" },
	{ key: "dispatch_report", value: "dispatch-report", label: "Dispatch Report", icon: "pi pi-truck" },
	{ key: "ironing_dpr", value: "ironing-dpr", label: "Ironing DPR", icon: "pi pi-sliders-h" },
	{ key: "finishing_plan_report", value: "finishing-plan-report", label: "Finishing Plan Report", icon: "pi pi-table" },
	{ key: "rejection_details", value: "rejection-details", label: "Rejection Details", icon: "pi pi-ban" },
	{ key: "rework_completion", value: "rework-completion", label: "Rework Completion", icon: "pi pi-check-square" },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", capabilityProps: lotCutQuantityProps },
	{ key: "inhouse_quantity", value: "inhouse-quantity", label: "In-house Quantity", icon: "pi pi-building" },
]

export function finishingReportTabs(reports = {}) {
	return [...readable(FINISHING_REPORTS, reports), ...departmentDeskReports("finishing", reports)]
}

export const QUALITY_REPORTS = [
	{ key: "quality_inspection_rft", value: "quality-inspection-rft", label: "Quality Inspection RFT", icon: "pi pi-verified", props: { reportKey: "quality-inspection-rft" } },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", capabilityProps: lotCutQuantityProps },
]

export function qualityReportTabs(reports = {}) {
	return readable(QUALITY_REPORTS, reports)
}

export function hrReportTabs(reports = {}) {
	return readable([{ key: "attendance", value: "attendance", label: "Attendance", icon: "pi pi-users" }], reports)
}

export const SALES_REPORTS = [
	{ key: "ppo_report", value: "ppo-report", label: "PPO Report", icon: "pi pi-file", capabilityProps: (report) => ({ canExport: Boolean(report?.can_export) }) },
	{ key: "finishing_dispatch", value: "finishing-dispatch", label: "Finishing Plan Dispatch", icon: "pi pi-truck" },
]

export function salesReportTabs(capabilities = {}) {
	return capabilities.sections?.reports?.can_read ? readable(SALES_REPORTS, capabilities.reports) : []
}

export const SEWING_REPORTS = [
	{ value: "status-summary", key: "status_summary", label: "Status Summary" },
	{ value: "dpr", key: "dpr", label: "DPR" },
	{ value: "scr", key: "scr", label: "SCR" },
	{ value: "monthly-summary", key: "monthly_summary", label: "Monthly Summary" },
	{ value: "item-summary", key: "item_summary", label: "Item Summary" },
	{ value: "finishing-dispatch", key: "finishing_dispatch", label: "Finishing Plan Dispatch" },
	{ value: "lot-cut-quantity", key: "lot_cut_quantity", label: "Lot Cut Quantity" },
	{ value: "inhouse-quantity", key: "inhouse_quantity", label: "In-house Quantity" },
]

export function sewingReportTabs(reports = {}) {
	return [...SEWING_REPORTS.filter((report) => reports?.[report.key]?.can_read), ...departmentDeskReports("sewing", reports)]
}

export const STORE_REPORTS = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse" },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", capabilityProps: lotCutQuantityProps },
]

/** Fabric, Accessory Store and Purchase reports: Desk reports show once any of the store's own reports is readable. */
export function storeReportTabs(reports = {}, department = "fabric-store", reportKeys = ["stock_balance"]) {
	const own = readable(STORE_REPORTS.filter((report) => reportKeys.includes(report.key)), reports)
	const allowed = reportKeys.some((key) => reports?.[key]?.can_read)
	return [...own, ...departmentDeskReports(department, reports, allowed)]
}

export const CUT_PANEL_REPORTS = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse" },
	{ key: "cut_bundle_balance", value: "cut-bundle-balance", label: "Cut Bundle Balance", icon: "pi pi-box" },
]

export function cutPanelReportTabs(reports = {}) {
	return [...readable(CUT_PANEL_REPORTS, reports), ...departmentDeskReports("cut-panel-store", reports)]
}
