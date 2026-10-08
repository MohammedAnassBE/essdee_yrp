import { callMethod, getMeta } from "./frappe.js"

const WORKSPACE_METHOD = "essdee_yrp.sewing.web_workspace"
const PLAN_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_sewing_plan.sd_yrp_sewing_plan"
const CLOSED_WO_METHOD = "essdee_yrp.sewing.closed_work_order"

export function getSewingCapabilities() {
	return callMethod(`${WORKSPACE_METHOD}.get_capabilities`)
}

export function getSewingDashboard(supplier) {
	return callMethod(`${PLAN_METHOD}.get_dashboard_data`, { supplier })
}

export function getSewingStatusSummary(supplier) {
	return callMethod(`${PLAN_METHOD}.get_sp_status_summary`, { supplier })
}

export function getSewingDpr(supplier, filters) {
	const common = { supplier, work_station: filters.workStation || "", input_type: filters.inputType || "" }
	return filters.mode === "range"
		? callMethod(`${PLAN_METHOD}.get_sewing_plan_dpr_summary`, { supplier, from_date: filters.fromDate, to_date: filters.toDate, work_station: common.work_station, input_type: common.input_type })
		: callMethod(`${PLAN_METHOD}.get_sewing_plan_dpr_data`, { supplier, dpr_date: filters.date, work_station: common.work_station, input_type: common.input_type })
}

export function getSewingScr(supplier, lot) {
	return callMethod(`${PLAN_METHOD}.get_scr_data`, { supplier, lot })
}

export function getSewingMonthlySummary(supplier, filters) {
	return callMethod(`${PLAN_METHOD}.get_monthly_summary_data`, {
		supplier, start_date: filters.fromDate, end_date: filters.toDate,
		input_type: filters.inputType || "", show_grn: filters.showGrn ? 1 : 0,
	})
}

export function getSewingItemSummaryOptions(supplier) {
	return callMethod(`${PLAN_METHOD}.get_item_summary_options`, { supplier })
}

export function getSewingItemSummary(supplier, filters) {
	return callMethod(`${PLAN_METHOD}.get_item_summary_data`, { supplier, lots: [...filters.lots], items: [...filters.items] })
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

export async function getClosedSewingWorkOrders(supplier, text = "") {
	if (!supplier) return []
	const rows = await callMethod(`${CLOSED_WO_METHOD}.get_closed_sewing_work_orders`, {
		doctype: "YRP Work Order", txt: text, searchfield: "name", start: 0, page_len: 20, filters: { supplier },
	})
	return (rows || []).map(([name, lot, item, process]) => ({ name, label: name, lot, item, process }))
}

export function getClosedWorkOrderGrnDetails(workOrder, supplier) {
	return callMethod(`${CLOSED_WO_METHOD}.get_closed_work_order_grn_details`, { work_order: workOrder, supplier })
}

export function createClosedWorkOrderGrn(payload) {
	return callMethod(`${CLOSED_WO_METHOD}.create_closed_work_order_grn`, payload)
}

export async function getClosedGrnNamingField() {
	const docs = await getMeta("YRP Goods Received Note")
	const field = docs.find(doc => doc.name === "YRP Goods Received Note")?.fields?.find(field => field.fieldname === "naming_series")
	if (!field) throw new Error("Goods Received Note naming series could not be loaded.")
	return field
}
