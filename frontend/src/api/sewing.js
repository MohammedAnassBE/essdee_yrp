import { callMethod } from "./frappe.js"

const WORKSPACE_METHOD = "essdee_yrp.sewing.web_workspace"

export function getSewingCapabilities() {
	return callMethod(`${WORKSPACE_METHOD}.get_capabilities`)
}
