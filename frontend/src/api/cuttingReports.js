import { callMethod } from "./frappe.js"

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

export function getStockBalanceReport(filters) {
	return callMethod("frappe.desk.query_report.run", {
		report_name: "YRP Stock Balance",
		filters: JSON.stringify(filters),
		// The standalone workspace does not have Desk's prepared-report polling
		// shell, so execute only after the user explicitly selects Generate.
		ignore_prepared_report: true,
		are_default_filters: true,
	})
}
