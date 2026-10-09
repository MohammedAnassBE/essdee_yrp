import { callMethod, downloadMethodFile } from "./frappe.js"

const METHOD = "essdee_yrp.sales.web_workspace"

export function getSalesCapabilities() {
	return callMethod(`${METHOD}.get_capabilities`)
}

export function getProductionOrderWorkspace(productionOrder) {
	return callMethod(`${METHOD}.get_production_order_workspace`, { production_order: productionOrder })
}

export function getProductionOrderEditor(name = null, source = null) {
	return callMethod(`${METHOD}.get_production_order_editor`, { name, source })
}

export function saveProductionOrder(values, options = {}) {
	return callMethod(`${METHOD}.save_production_order`, {
		values,
		name: options.name || null,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || null,
	})
}

export function executeProductionOrderCommand(name, command, payload = {}, expectedModified = null) {
	return callMethod(`${METHOD}.execute_production_order_command`, {
		name,
		command,
		payload,
		expected_modified: expectedModified,
	})
}

export function getPpoReport(filters = {}) {
	return callMethod(`${METHOD}.get_ppo_report`, { filters })
}

export function getPpoDispatchSummary(productionOrder) {
	return callMethod(`${METHOD}.get_ppo_dispatch_summary`, { production_order: productionOrder })
}

export function downloadPpoReport(filters = {}) {
	return downloadMethodFile(`${METHOD}.download_ppo_report`, filters, "PPO_Report.xlsx")
}
