import { callMethod } from "./frappe.js"

const WORKSPACE_METHOD = "essdee_yrp.cut_panel_store.web_workspace"

export function getCutPanelStoreCapabilities() {
	return callMethod(`${WORKSPACE_METHOD}.get_capabilities`)
}
