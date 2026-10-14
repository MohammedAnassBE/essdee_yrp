import { callMethod, downloadMethodFile } from "./frappe.js"

const WEB_REPORT_METHOD = "yrp.api.web_reports"

export function runWebReport(reportKey, filters, refresh = false) {
	return callMethod(`${WEB_REPORT_METHOD}.run_web_report`, {
		report_key: reportKey,
		filters,
		refresh: refresh ? 1 : 0,
	})
}

export function getReportJob(reportKey, jobName, includeResult = false) {
	return callMethod(`${WEB_REPORT_METHOD}.get_report_job`, {
		report_key: reportKey,
		job_name: jobName,
		include_result: includeResult ? 1 : 0,
	})
}

export function downloadReportJob(reportKey, jobName) {
	return downloadMethodFile(`${WEB_REPORT_METHOD}.download_report_job`, {
		report_key: reportKey,
		job_name: jobName,
	}, `${reportKey}.json`)
}

export function getReportLayout(reportKey) {
	return callMethod(`${WEB_REPORT_METHOD}.get_report_layout`, { report_key: reportKey })
}

export function saveReportLayout(reportKey, columns) {
	return callMethod(`${WEB_REPORT_METHOD}.save_report_layout`, {
		report_key: reportKey,
		columns,
	})
}

export function resetReportLayout(reportKey) {
	return callMethod(`${WEB_REPORT_METHOD}.reset_report_layout`, { report_key: reportKey })
}

export function getLinkFieldOptions(reportKey, sourceColumn) {
	return callMethod(`${WEB_REPORT_METHOD}.get_link_field_options`, {
		report_key: reportKey,
		source_column: sourceColumn,
	})
}

export function getLinkedValues(reportKey, requests, requestOptions = {}) {
	return callMethod(`${WEB_REPORT_METHOD}.get_linked_values`, {
		report_key: reportKey,
		requests,
	}, requestOptions)
}
