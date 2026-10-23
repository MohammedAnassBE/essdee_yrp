import { defineAsyncComponent as lazy, reactive } from "vue"

import { visibleProductionReports } from "../planningViews.js"

const SewingUnitReport = lazy(() => import("./SewingUnitReport.vue"))
const StockBalanceReport = lazy(() => import("../../../components/reports/StockBalanceReport.vue"))
const LotCutQuantityReport = lazy(() => import("../../../components/reports/LotCutQuantityReport.vue"))
const MultiCCRReport = lazy(() => import("../../cutting/reports/MultiCCRReport.vue"))
const FinishingDispatchReport = lazy(() => import("../../finishing/reports/FinishingDispatchReport.vue"))
const FinishingPlanReport = lazy(() => import("../../finishing/reports/FinishingPlanReport.vue"))
const InhouseQuantityReport = lazy(() => import("./InhouseQuantityReport.vue"))
const lotCutProps = capability => ({ canReadCuttingPlan: Boolean(capability.can_read_cutting_plan) })

const CUTTING_REPORTS = [
	{ key: "daily-production", label: "Daily Production", icon: "pi pi-chart-line", component: lazy(() => import("../../cutting/reports/DailyProductionReport.vue")) },
	{ key: "daily-cut-sheet", label: "Daily Cut Sheet", icon: "pi pi-table", component: lazy(() => import("../../cutting/reports/DailyCutSheetReport.vue")) },
	{ key: "multi-ccr", label: "Multi CCR", icon: "pi pi-chart-scatter", component: MultiCCRReport },
	{ key: "cutting-detail", label: "Cutting Detail", icon: "pi pi-chart-bar", component: lazy(() => import("../../cutting/reports/CuttingDetailReport.vue")) },
	{ key: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse", component: StockBalanceReport },
]

/** `unitFilters` marks reports scoped to one Sewing Unit; its value seeds the report's filters. */
const SEWING_REPORTS = [
	{ key: "status_summary", value: "status-summary", label: "Status Summary", icon: "pi pi-list-check", component: lazy(() => import("../../sewing/reports/SewingStatusSummary.vue")), unitFilters: () => ({ lot: [], item: [], colour: [], part: [], fromDate: "", toDate: "" }) },
	{ key: "dpr", value: "dpr", label: "Sewing DPR", icon: "pi pi-chart-line", component: lazy(() => import("../../sewing/reports/SewingDpr.vue")), unitFilters: () => ({ mode: "daily", date: "", fromDate: "", toDate: "", workStation: "", inputType: "", lot: "", item: "" }) },
	{ key: "scr", value: "scr", label: "SCR", icon: "pi pi-table", component: lazy(() => import("../../sewing/reports/SewingScr.vue")), unitFilters: () => ({ lot: "", colours: [] }) },
	{ key: "monthly_summary", value: "monthly-summary", label: "Monthly Summary", icon: "pi pi-calendar", component: lazy(() => import("../../sewing/reports/SewingMonthlySummary.vue")), unitFilters: () => ({ fromDate: "", toDate: "", inputType: "", showGrn: false }) },
	{ key: "item_summary", value: "item-summary", label: "Item Summary", icon: "pi pi-box", component: lazy(() => import("../../sewing/reports/SewingItemSummary.vue")), unitFilters: () => ({ lots: [], items: [] }) },
	{ key: "finishing_dispatch", value: "finishing-dispatch", label: "Finishing Plan Dispatch", icon: "pi pi-truck", component: FinishingDispatchReport },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", component: LotCutQuantityReport, capabilityProps: lotCutProps },
	{ key: "inhouse_quantity", value: "inhouse-quantity", label: "In-house Quantity", icon: "pi pi-building", component: InhouseQuantityReport },
]

const FINISHING_REPORTS = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse", component: StockBalanceReport },
	{ key: "packing_dpr", value: "packing-dpr", label: "Packing DPR", icon: "pi pi-box", component: lazy(() => import("../../finishing/reports/FinishingPackingDpr.vue")) },
	{ key: "dispatch_report", value: "dispatch-report", label: "Dispatch Report", icon: "pi pi-truck", component: FinishingDispatchReport },
	{ key: "ironing_dpr", value: "ironing-dpr", label: "Ironing DPR", icon: "pi pi-sliders-h", component: lazy(() => import("../../finishing/reports/FinishingIroningDpr.vue")) },
	{ key: "finishing_plan_report", value: "finishing-plan-report", label: "Finishing Plan Report", icon: "pi pi-table", component: FinishingPlanReport },
	{ key: "rejection_details", value: "rejection-details", label: "Rejection Details", icon: "pi pi-ban", component: lazy(() => import("../../finishing/reports/FinishingRejectionReport.vue")) },
	{ key: "rework_completion", value: "rework-completion", label: "Rework Completion", icon: "pi pi-check-square", component: lazy(() => import("../../finishing/reports/FinishingReworkCompletion.vue")) },
	{ key: "lot_cut_quantity", value: "lot-cut-quantity", label: "Lot Cut Quantity", icon: "pi pi-th-large", component: LotCutQuantityReport, capabilityProps: lotCutProps },
]

const PRODUCTION_COMPONENTS = {
	work_order: lazy(() => import("./WorkOrderReport.vue")),
	dispatch_percentage: lazy(() => import("./DispatchPercentageReport.vue")),
	work_order_pending: lazy(() => import("./WorkOrderPendingReport.vue")),
	finishing_plan: FinishingPlanReport,
	inward_quantity: lazy(() => import("./InwardQuantityReport.vue")),
	inhouse_quantity: InhouseQuantityReport,
	month_wise_detail: lazy(() => import("./MonthWiseDetailReport.vue")),
	process_pending: lazy(() => import("./ProcessPendingReport.vue")),
	size_wise_stock: lazy(() => import("./SizeWiseStockReport.vue")),
	colour_wise_diff: lazy(() => import("./ColourWiseDiffReport.vue")),
	work_in_progress: lazy(() => import("./WorkInProgressReport.vue")),
	multi_ccr: MultiCCRReport,
	ppo_report: lazy(() => import("../../sales/PpoReport.vue")),
	work_order_bulk_close: lazy(() => import("./WorkOrderBulkClose.vue")),
}

export const PLANNING_REPORT_GROUPS = { cutting: "Cutting", sewing: "Sewing", finishing: "Finishing", production: "Production / WIP" }

function cuttingReports(permissions = {}) {
	return CUTTING_REPORTS.filter(report => permissions[report.key])
		.map(report => ({ ...report, value: `cutting-${report.key}`, group: PLANNING_REPORT_GROUPS.cutting }))
}

function sewingReports(capabilities = {}) {
	if (!capabilities.sections?.reports?.can_read) return []
	return SEWING_REPORTS.filter(report => capabilities.reports?.[report.key]?.can_read && capabilities.reports[report.key].can_report).map(report => {
		const reportProps = report.capabilityProps?.(capabilities.reports[report.key]) || {}
		const unitProps = report.unitFilters && { component: SewingUnitReport, props: { report: report.component, reportProps: { filters: reactive(report.unitFilters()) } } }
		return { ...report, value: `sewing-${report.value}`, group: PLANNING_REPORT_GROUPS.sewing, props: reportProps, ...unitProps }
	})
}

function finishingReports(capabilities = {}) {
	const reports = capabilities.sections?.reports?.reports || {}
	return FINISHING_REPORTS.filter(report => reports[report.key]?.can_read)
		.map(report => ({ ...report, value: `finishing-${report.value}`, group: PLANNING_REPORT_GROUPS.finishing, props: report.capabilityProps?.(reports[report.key]) }))
}

function productionReports(reports = {}) {
	const props = { work_order_bulk_close: { permissions: reports.work_order_bulk_close }, ppo_report: { canExport: Boolean(reports.ppo_report?.can_export) } }
	return visibleProductionReports(reports).map(report => ({ ...report, group: PLANNING_REPORT_GROUPS.production, component: PRODUCTION_COMPONENTS[report.key], props: props[report.key] }))
}

/** Every Planning report the viewer may open, grouped by source department. */
export function planningReports({ cutting, sewing, finishing, production } = {}) {
	return [...cuttingReports(cutting), ...sewingReports(sewing), ...finishingReports(finishing), ...productionReports(production)]
}

/** Maps a pre-merge `?group=&report=` (or Sewing `tab`) link onto the combined report value. */
export function legacyPlanningReportQuery(query = {}) {
	const { group, tab, ...rest } = query
	if (!group) return null
	const report = query.report || tab
	return group === "production" || !report ? rest : { ...rest, report: `${group}-${report}` }
}
