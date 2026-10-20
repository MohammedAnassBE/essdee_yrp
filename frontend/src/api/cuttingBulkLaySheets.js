import { callMethod } from "./frappe.js"

const METHOD = "essdee_yrp.cutting.bulk_laysheets_workspace"
const LAYSHEET_METHOD = "essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet"

function call(name, args = {}, options = {}) {
	return callMethod(`${METHOD}.${name}`, args, options)
}

export function getBulkLaySheetsEditor(name = "") {
	return call("get_editor", name ? { name } : {})
}

export function saveBulkLaySheets(values, { name = "", expectedModified = "" } = {}) {
	return call("save", { values, name: name || null, expected_modified: expectedModified || null })
}

export function getBulkLaySheetsWorkspace(name) {
	return call("get_workspace", { name })
}

export function createBulkLaySheets(name) {
	return call("create_laysheets", { doc_name: name })
}

export function activateBulkLaySheet(name, cuttingLaySheet) {
	return call("set_active_laysheet", { doc_name: name, cutting_laysheet: cuttingLaySheet })
}

export function saveBulkActiveEditor(name, detailName, itemDetails, itemAccessories, expectedModified = "") {
	return call("save_active_editor", {
		doc_name: name,
		detail_name: detailName,
		item_details: itemDetails,
		item_accessory_details: itemAccessories,
		expected_modified: expectedModified || null,
	})
}

export function generateBulkBundles(name, detailName, values) {
	return call("generate_bundles", {
		doc_name: name,
		detail_name: detailName,
		groups: values.groups,
		bundle_generated_date: values.bundle_generated_date,
		maximum_no_of_plys: values.maximum_no_of_plys,
		maximum_allow_percentage: values.maximum_allow_percentage,
	})
}

export function createBulkRowTransfer(name, detailName) {
	return call("create_lot_transfer", { doc_name: name, detail_name: detailName })
}

export function submitBulkRowTransfer(name, detailName) {
	return call("submit_lot_transfer", { doc_name: name, detail_name: detailName })
}

export function createSharedBulkTransfer(name) {
	return call("create_bulk_lot_transfer", { doc_name: name })
}

export function submitSharedBulkTransfer(name) {
	return call("submit_bulk_lot_transfer", { doc_name: name })
}

export function getBulkDeliverySetup(name) {
	return call("get_delivery_challan_setup", { doc_name: name })
}

export function createBulkRowDelivery(name, detailName, namingSeries, vehicleNo) {
	return call("create_delivery_challan", { doc_name: name, detail_name: detailName, naming_series: namingSeries, vehicle_no: vehicleNo })
}

export function createAllBulkDeliveries(name, namingSeries, vehicleNo) {
	return call("create_bulk_delivery_challans", { doc_name: name, naming_series: namingSeries, vehicle_no: vehicleNo })
}

export function submitBulkRowDelivery(name, detailName) {
	return call("submit_delivery_challan", { doc_name: name, detail_name: detailName })
}

export function approveBulkGrammage(name, detailName) {
	return call("approve_grammage", { doc_name: name, detail_name: detailName }, { silent: true })
}

export function getBulkPrintContext(name, detailName) {
	return call("get_print_context", { doc_name: name, detail_name: detailName })
}

export function completeBulkLabelPrint(name, detailName, goodsReceivedNote = "") {
	return call("complete_label_print", { doc_name: name, detail_name: detailName, goods_received_note: goodsReceivedNote || null })
}

export function getBulkMarkerParts(cuttingMarker) {
	return callMethod(`${LAYSHEET_METHOD}.get_parts`, { cutting_marker: cuttingMarker })
}

export function prepareBulkLabels(context, printOrder) {
	return callMethod(`${LAYSHEET_METHOD}.print_labels`, {
		print_items: context.print_items,
		lay_no: context.lay_no,
		doc_name: context.cutting_laysheet,
		print_order: printOrder,
		cutting_plan: context.cutting_plan,
	})
}
