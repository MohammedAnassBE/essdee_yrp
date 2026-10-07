import { callMethod } from "./frappe.js"

const WORKSPACE_METHOD = "essdee_yrp.cut_panel_store.web_workspace"
const MOVEMENT_METHOD = "essdee_yrp.cut_panel_store.movement_workspace"
const CUT_BUNDLE_METHOD = "essdee_yrp.cut_panel_store.cut_bundle_workspace"

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
