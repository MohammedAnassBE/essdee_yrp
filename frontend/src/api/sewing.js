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

export function getSewingEntries(supplier, filters = {}) {
	return callMethod(`${PLAN_METHOD}.get_sewing_plan_entries`, {
		supplier, work_station: filters.workStation || "", input_type: filters.inputType || "", lot_name: filters.lot || "",
	})
}

export function cancelSewingEntry(docId) {
	return callMethod(`${PLAN_METHOD}.cancel_sewing_plan_entry`, { doc_id: docId })
}

export async function getSewingSupplierLots(supplier, text = "") {
	if (!supplier) return []
	const rows = await callMethod(`${PLAN_METHOD}.get_supplier_lots`, {
		doctype: "SD YRP Lot", txt: text, searchfield: "name", start: 0, page_len: 20, filters: { supplier },
	})
	return (rows || []).map(([name, item]) => ({ name, label: name, item }))
}

export function getSewingConsumption(supplier, lot) {
	return callMethod(`${PLAN_METHOD}.get_consumption_mapping_data`, { supplier, lot })
}

export function saveSewingConsumption(supplier, lot, sections, clothAccData) {
	return callMethod(`${PLAN_METHOD}.save_consumption_data`, { supplier, lot, sections, cloth_acc_data: clothAccData })
}
