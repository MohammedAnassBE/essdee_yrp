import { callMethod } from "./frappe.js"

const WORKSPACE_METHOD = "essdee_yrp.sewing.web_workspace"
const PLAN_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_sewing_plan.sd_yrp_sewing_plan"

export function getSewingCapabilities() {
	return callMethod(`${WORKSPACE_METHOD}.get_capabilities`)
}

export function getSewingDashboard(supplier) {
	return callMethod(`${PLAN_METHOD}.get_dashboard_data`, { supplier })
}

export function getSewingDataEntry(supplier, lot = "") {
	return callMethod(`${PLAN_METHOD}.get_data_entry_data`, { supplier, lot })
}

export function submitSewingDataEntry(payload) {
	return callMethod(`${PLAN_METHOD}.submit_data_entry_log`, { payload })
}

export function updateSewingInspection(payload) {
	return callMethod(`${PLAN_METHOD}.update_sewing_plan_data`, { payload })
}
