import { callMethod } from "./frappe.js"

export { getStockBalanceReport } from "./stockReports.js"

const REPORTS_METHOD = "essdee_yrp.cutting.reports"

export function getCuttingReportPermissions() {
	return callMethod(`${REPORTS_METHOD}.get_report_permissions`)
}

export function getDailyProductionReport(filters) {
	return callMethod(`${REPORTS_METHOD}.get_daily_production_report`, filters)
}

export function getDailyProductionSummary(filters) {
	return callMethod(`${REPORTS_METHOD}.get_daily_production_summary_report`, {
		...filters,
		items: JSON.stringify(filters.items || []),
		lots: JSON.stringify(filters.lots || []),
	})
}

export function getDailyCutSheetReport(filters) {
	return callMethod(`${REPORTS_METHOD}.get_cut_sheet_report`, filters)
}

export function getCuttingDetailReport(filters) {
	return callMethod(`${REPORTS_METHOD}.get_cutting_detail_report`, filters)
}

export function getMultiCcrReport(filters) {
	return callMethod(`${REPORTS_METHOD}.get_multiccr`, filters)
}
