import { callMethod } from "./frappe.js"

export function getStockBalanceReport(filters) {
	return callMethod("frappe.desk.query_report.run", {
		report_name: "YRP Stock Balance",
		filters: JSON.stringify(filters),
		// This web workspace has no prepared-report polling shell, so the
		// query runs only after the operator explicitly selects Generate.
		ignore_prepared_report: true,
		are_default_filters: true,
	})
}
