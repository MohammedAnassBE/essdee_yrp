import { callMethod, callRead, downloadMethodFile } from "./frappe.js"

const WORKSPACE_METHOD = "essdee_yrp.finishing.web_workspace"

export function getFinishingCapabilities() {
	return callRead(`${WORKSPACE_METHOD}.get_capabilities`)
}

export function getFinishingPlanWorkspace(name) {
	return callMethod(`${WORKSPACE_METHOD}.get_plan_workspace`, { name })
}

export function getFinishingPlanTab(name, tab) {
	return callMethod(`${WORKSPACE_METHOD}.get_plan_tab`, { name, tab })
}

export function executeFinishingPlanCommand(name, command, payload = {}, expectedModified = "") {
	return callMethod(`${WORKSPACE_METHOD}.execute_plan_command`, {
		name,
		command,
		payload,
		expected_modified: expectedModified,
	})
}

export function prepareFinishingInwardPrint(name, size) {
	return callMethod(`${WORKSPACE_METHOD}.prepare_inward_print`, { name, size })
}

export async function searchUnconfiguredLots(text = "") {
	const rows = await callMethod("essdee_yrp.finishing.alternative.get_unconfigured_lots", {
		doctype: "SD YRP Lot",
		txt: text,
		searchfield: "name",
		start: 0,
		page_len: 20,
		filters: {},
	})
	return (rows || []).map((row) => ({ name: Array.isArray(row) ? row[0] : row.name, label: Array.isArray(row) ? row[0] : row.name }))
}

const REPORTS_METHOD = "essdee_yrp.finishing.web_reports"
const DISPATCH_METHOD = "essdee_yrp.finishing.web_dispatch"
const REWORK_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item.sd_yrp_grn_rework_item"

export const getPackingDpr = (filters) => callMethod(`${REPORTS_METHOD}.get_packing_dpr`, filters)
export const getDispatchReport = (filters) => callMethod(`${REPORTS_METHOD}.get_dispatch_report`, filters)
export const getIroningDpr = (filters) => callMethod(`${REPORTS_METHOD}.get_ironing_dpr`, filters)
export const getRejectionDetails = (filters) => callMethod(`${REPORTS_METHOD}.get_rejection_details`, filters)
export const downloadRejectionDetails = (filters) => downloadMethodFile(`${REPORTS_METHOD}.download_rejection_details`, filters, "rejection_details.xlsx")
export const getReworkCompletion = (filters) => callMethod(`${REPORTS_METHOD}.get_rework_completion`, filters)
export const getReworkDetails = (filters) => callMethod(`${REPORTS_METHOD}.get_rework_details`, filters)
export const downloadReworkDetails = (filters) => downloadMethodFile(`${REPORTS_METHOD}.download_rework_details`, filters, "rework_details.xlsx")
export const updateReworkRejection = (rows, completed, lot) => callMethod(`${REWORK_METHOD}.update_rejected_quantity`, { rejection_data: rows, completed, lot })
export const updateReworkPartial = (rows, lot) => callMethod(`${REWORK_METHOD}.update_partial_quantity`, { data: rows, lot })

export const getDispatchWorkspace = (name = "") => callMethod(`${DISPATCH_METHOD}.get_dispatch_workspace`, { name: name || null })
export const fetchDispatchItems = () => callMethod(`${DISPATCH_METHOD}.fetch_dispatch_items`)
export function saveDispatch(items, name = "", submit = false, expectedModified = "") {
	return callMethod(`${DISPATCH_METHOD}.save_dispatch`, { items, name: name || null, submit: submit ? 1 : 0, expected_modified: expectedModified || null })
}
export function executeDispatchCommand(name, command, payload = {}, expectedModified = "") {
	return callMethod(`${DISPATCH_METHOD}.execute_dispatch_command`, { name, command, payload, expected_modified: expectedModified })
}
export const getSupplierWarehouses = (supplier) => callMethod("essdee_yrp.finishing.dispatch_locations.get_supplier_warehouses", { supplier })
