import { callMethod, callRead } from "./frappe.js"

const IPD_METHOD = "essdee_yrp.merch.ipd_workspace"
const LOT_METHOD = "essdee_yrp.merch.lot_workspace"

export function getMerchLotWorkspace(name) {
	return callMethod(`${LOT_METHOD}.get_merch_lot_workspace`, { name })
}

export function getMerchLotEditor(name = null, duplicateFrom = null) {
	return callMethod(`${LOT_METHOD}.get_merch_lot_editor`, { name, duplicate_from: duplicateFrom })
}

export function saveMerchLot(values, { name = null, expectedModified = null } = {}) {
	return callMethod(`${LOT_METHOD}.save_merch_lot`, { values, name, expected_modified: expectedModified })
}

export function executeMerchLotCommand(name, command, payload, expectedModified) {
	return callMethod(`${LOT_METHOD}.execute_merch_lot_command`, { name, command, payload, expected_modified: expectedModified })
}

export function getMerchClothProgramContext(lot) {
	return callMethod("essdee_yrp.api.cloth_program.get_cloth_program_context", { lot })
}

export function getMerchYarnProfile(yarnItem) {
	return callMethod("essdee_yrp.api.cloth_program.get_yarn_profile", { yarn_item: yarnItem })
}

export function getMerchCapabilities() {
	return callRead("essdee_yrp.merch.web_workspace.get_capabilities")
}

export function getMerchPurchaseCapabilities() {
	return callRead("essdee_yrp.merch_purchase.web_workspace.get_capabilities")
}

export function getMerchPdCapabilities() {
	return callRead("essdee_yrp.merch_pd.web_workspace.get_capabilities")
}

export function getIpdListCapabilities() {
	return callRead(`${IPD_METHOD}.get_ipd_list_capabilities`)
}

export function getIpdWorkspace(name) {
	return callMethod(`${IPD_METHOD}.get_ipd_workspace`, { name })
}

export function getIpdEditor(name = null, duplicateFrom = null) {
	return callMethod(`${IPD_METHOD}.get_ipd_editor`, { name: name || null, duplicate_from: duplicateFrom || null })
}

export function getIpdGrids(name, values, grids) {
	return callMethod(`${IPD_METHOD}.get_ipd_grids`, { name, values, grids })
}

export function checkIpd(name = null, values = null) {
	return callMethod(`${IPD_METHOD}.check_ipd`, { name: name || null, values })
}

export function saveIpd(values, { name = null, expectedModified = null, duplicateFrom = null } = {}) {
	return callMethod(`${IPD_METHOD}.save_ipd`, {
		values, name: name || null, expected_modified: expectedModified || null, duplicate_from: duplicateFrom || null,
	})
}

export function executeIpdCommand(name, command, { payload = null, expectedModified = null } = {}) {
	return callMethod(`${IPD_METHOD}.execute_ipd_command`, {
		name, command, payload, expected_modified: expectedModified || null,
	})
}

export function getIpdCopyOptions(source) {
	return callMethod(`${IPD_METHOD}.get_ipd_copy_options`, { source })
}

export function copyIpd(source, { techPackVersion, patternVersion, sections, item = null }) {
	return callMethod(`${IPD_METHOD}.copy_ipd`, {
		source, tech_pack_version: techPackVersion, pattern_version: patternVersion, sections, item: item || null,
	})
}

export function getIpdChanges(name) {
	return callMethod(`${IPD_METHOD}.get_ipd_changes`, { name })
}

export function getAttributeValueUsage(name, attribute, values, draft = null) {
	return callMethod(`${IPD_METHOD}.get_attribute_value_usage`, { name, attribute, values, draft })
}

export function saveIpdAttributeValues(name, attribute, values, mappingModified) {
	return callMethod(`${IPD_METHOD}.save_ipd_attribute_values`, {
		name, attribute, values, mapping_modified: mappingModified,
	})
}

export function getIpdBomMapping(name, bomRow, tables = null) {
	return callMethod(`${IPD_METHOD}.get_ipd_bom_mapping`, {
		name, bom_row: bomRow, ...(tables || {}),
	})
}

export function saveIpdBomMapping(name, bomRow, rows, mappingModified, tables = null) {
	return callMethod(`${IPD_METHOD}.save_ipd_bom_mapping`, {
		name, bom_row: bomRow, rows, mapping_modified: mappingModified, ...(tables || {}),
	})
}

export function getIpdItemGroups() {
	return callMethod("essdee_yrp.ipd_ui.get_ipd_item_group")
}

const PROCESS_COST_METHOD = "essdee_yrp.merch.process_cost_workspace"

export function getProcessCostListCapabilities() {
	return callMethod(`${PROCESS_COST_METHOD}.get_process_cost_list_capabilities`)
}

export function getProcessCostWorkspace(name) {
	return callMethod(`${PROCESS_COST_METHOD}.get_process_cost_workspace`, { name })
}

export function getProcessCostEditor(name = null, lot = null, duplicateFrom = null) {
	return callMethod(`${PROCESS_COST_METHOD}.get_process_cost_editor`, { name, lot, duplicate_from: duplicateFrom })
}

export function getProcessCostGrid(values) {
	const { lot, process_name, item, attribute } = values
	return callMethod(`${PROCESS_COST_METHOD}.get_process_cost_grid`, { lot, process_name, item, attribute })
}

export function saveProcessCost(values, name = null, expectedModified = null) {
	return callMethod(`${PROCESS_COST_METHOD}.save_process_cost`, { values, name, expected_modified: expectedModified })
}

export function executeProcessCostCommand(name, action, expectedModified) {
	return callMethod(`${PROCESS_COST_METHOD}.execute_process_cost_command`, { name, action, expected_modified: expectedModified })
}

export function deleteProcessCost(name, expectedModified) {
	return callMethod(`${PROCESS_COST_METHOD}.delete_process_cost`, { name, expected_modified: expectedModified })
}

export async function searchProcessCostAttributes(values, text = "") {
	return callMethod(`${PROCESS_COST_METHOD}.search_process_cost_attributes`, {
		item: values.item, lot: values.lot, process_name: values.process_name, text,
	})
}
