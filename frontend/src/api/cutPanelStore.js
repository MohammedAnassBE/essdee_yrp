import { callMethod } from "./frappe.js"

const WORKSPACE_METHOD = "essdee_yrp.cut_panel_store.web_workspace"
const MOVEMENT_METHOD = "essdee_yrp.cut_panel_store.movement_workspace"
const CUT_BUNDLE_METHOD = "essdee_yrp.cut_panel_store.cut_bundle_workspace"
const BOX_STICKER_METHOD = "essdee_yrp.cut_panel_store.box_sticker_workspace"
const EXCEL_STICKER_METHOD = "essdee_yrp.cut_panel_store.excel_sticker_workspace"
const REPORT_METHOD = "essdee_yrp.cut_panel_store.report_workspace"

export function getCutPanelStoreCapabilities() {
	return callMethod(`${WORKSPACE_METHOD}.get_capabilities`)
}

export function getCutPanelMovementEditor(name = "", source = {}) {
	return callMethod(`${MOVEMENT_METHOD}.get_movement_editor`, {
		name: name || undefined,
		source: Object.keys(source || {}).length ? source : undefined,
	})
}

export function generateCutPanelMovementBundles(values) {
	return callMethod(`${MOVEMENT_METHOD}.generate_movement_bundles`, { values })
}

export function saveCutPanelMovement(values, options = {}) {
	return callMethod(`${MOVEMENT_METHOD}.save_movement`, {
		values,
		name: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || undefined,
	})
}

export function executeCutPanelMovementCommand(name, command, expectedModified = "") {
	return callMethod(`${MOVEMENT_METHOD}.execute_movement_command`, {
		name,
		command,
		expected_modified: expectedModified || undefined,
	})
}

export function getCutPanelMovementLinkedDocuments(name) {
	return callMethod(`${MOVEMENT_METHOD}.get_movement_linked_documents`, { name })
}

export function getCutPanelMovementWorkOrders(name, txt = "") {
	return callMethod(`${MOVEMENT_METHOD}.get_movement_work_orders`, { name, txt })
}

export function createCutPanelMovementTransaction(name, operation, values = {}, submit = false) {
	return callMethod(`${MOVEMENT_METHOD}.create_movement_transaction`, {
		name,
		operation,
		values,
		submit,
	})
}

export function getCutBundleEditor(name = "", source = {}) {
	return callMethod(`${CUT_BUNDLE_METHOD}.get_cut_bundle_editor`, {
		name: name || undefined,
		source: Object.keys(source || {}).length ? source : undefined,
	})
}

export function previewCutBundleSource(lot, warehouse, values = {}, name = "") {
	return callMethod(`${CUT_BUNDLE_METHOD}.preview_cut_bundle_source`, { lot, warehouse, values, name: name || undefined })
}

export function saveCutBundle(values, options = {}) {
	return callMethod(`${CUT_BUNDLE_METHOD}.save_cut_bundle`, {
		values,
		name: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || undefined,
	})
}

export function executeCutBundleCommand(name, command, expectedModified = "") {
	return callMethod(`${CUT_BUNDLE_METHOD}.execute_cut_bundle_command`, {
		name,
		command,
		expected_modified: expectedModified || undefined,
	})
}

export function getCutBundlePrintData(name, printer) {
	return callMethod(`${CUT_BUNDLE_METHOD}.get_cut_bundle_print_data`, { name, printer })
}

export function confirmCutBundlePrint(name, expectedModified = "", confirmationToken = "") {
	return callMethod(`${CUT_BUNDLE_METHOD}.confirm_cut_bundle_print`, {
		name,
		expected_modified: expectedModified || undefined,
		confirmation_token: confirmationToken || undefined,
	})
}

export function getBoxStickerEditor(name = "", source = {}) {
	return callMethod(`${BOX_STICKER_METHOD}.get_box_sticker_editor`, {
		name: name || undefined,
		source: Object.keys(source || {}).length ? source : undefined,
	})
}

export function previewBoxStickerSource(lot = "", fgItem = "", values = {}, name = "") {
	return callMethod(`${BOX_STICKER_METHOD}.preview_box_sticker_source`, {
		lot: lot || undefined,
		fg_item: fgItem || undefined,
		values,
		name: name || undefined,
	})
}

export function saveBoxSticker(values, options = {}) {
	return callMethod(`${BOX_STICKER_METHOD}.save_box_sticker`, {
		values,
		name: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || undefined,
	})
}

export function executeBoxStickerCommand(name, command, expectedModified = "") {
	return callMethod(`${BOX_STICKER_METHOD}.execute_box_sticker_command`, {
		name,
		command,
		expected_modified: expectedModified || undefined,
	})
}

export function getBoxStickerPreview(name) {
	return callMethod(`${BOX_STICKER_METHOD}.get_box_sticker_preview`, { name })
}

export function getConfiguredBoxStickerPrinters(printers = []) {
	return callMethod(`${BOX_STICKER_METHOD}.get_configured_box_sticker_printers`, { printers })
}

export function reserveBoxStickerPrint(name, rows, printerType, requestId, expectedModified = "") {
	return callMethod(`${BOX_STICKER_METHOD}.reserve_box_sticker_print`, {
		name,
		rows,
		printer_type: printerType,
		request_id: requestId,
		expected_modified: expectedModified || undefined,
	})
}

export function confirmBoxStickerPrint(reservation) {
	return callMethod(`${BOX_STICKER_METHOD}.confirm_box_sticker_print`, { reservation })
}

export function rollbackBoxStickerPrint(reservation) {
	return callMethod(`${BOX_STICKER_METHOD}.rollback_box_sticker_print`, { reservation })
}

export function getBoxStickerPrintRecovery(requestId) {
	return callMethod(`${BOX_STICKER_METHOD}.get_box_sticker_print_recovery`, { request_id: requestId })
}

export function getExcelStickerEditor(name = "") {
	return callMethod(`${EXCEL_STICKER_METHOD}.get_excel_sticker_editor`, {
		name: name || undefined,
	})
}

export function saveExcelSticker(values, options = {}) {
	return callMethod(`${EXCEL_STICKER_METHOD}.save_excel_sticker`, {
		values,
		name: options.name || undefined,
		expected_modified: options.expectedModified || undefined,
	})
}

export function executeExcelStickerCommand(name, command, expectedModified = "") {
	return callMethod(`${EXCEL_STICKER_METHOD}.execute_excel_sticker_command`, {
		name,
		command,
		expected_modified: expectedModified || undefined,
	})
}

export function getExcelStickerPreview(name) {
	return callMethod(`${EXCEL_STICKER_METHOD}.get_excel_sticker_preview`, { name })
}

export function getExcelStickerPrintData(name, printerType) {
	return callMethod(`${EXCEL_STICKER_METHOD}.get_excel_sticker_print_data`, {
		name,
		printer_type: printerType,
	})
}

export function getCutBundleBalance(filters = {}) {
	return callMethod(`${REPORT_METHOD}.get_cut_bundle_balance`, { filters })
}
