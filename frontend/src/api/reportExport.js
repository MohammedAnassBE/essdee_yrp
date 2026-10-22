import { callMethod, downloadMethodFile } from "./frappe.js"

const EXPORT_METHOD = "essdee_yrp.report_export"

const permissionRequests = new Map()

export function getExportPermission({ reportKey, doctype }) {
	const key = reportKey ? `report:${reportKey}` : `doctype:${doctype}`
	if (!permissionRequests.has(key)) {
		const args = reportKey ? { report_key: reportKey } : { doctype }
		permissionRequests.set(key, callMethod(`${EXPORT_METHOD}.get_export_permission`, args).then(Boolean, () => {
			permissionRequests.delete(key)
			return false
		}))
	}
	return permissionRequests.get(key)
}

export function exportWebReport(args, fallbackName) {
	return downloadMethodFile(`${EXPORT_METHOD}.export_web_report`, args, fallbackName)
}

export function exportReportRows(args, fallbackName) {
	return downloadMethodFile(`${EXPORT_METHOD}.export_report_rows`, args, fallbackName)
}
