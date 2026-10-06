import { callMethod } from "./frappe.js"

const METHOD = "essdee_yrp.cutting.planner_workspace"
const call = (name, args = {}) => callMethod(`${METHOD}.${name}`, args)

export function getLaySheetPlannerEditor(name = "") {
	return call("get_editor", name ? { name } : {})
}

export function saveLaySheetPlanner(values, { name = "", expectedModified = "" } = {}) {
	return call("save", { values, name: name || null, expected_modified: expectedModified || null })
}

export function startLaySheetOptimization(name, expectedModified = "") {
	return call("start_optimization", { name, expected_modified: expectedModified || null })
}

export function getLaySheetOptimizationStatus(name) {
	return call("get_status", { name })
}

export function selectLaySheetStrategy(name, strategy, expectedModified = "") {
	return call("select_result", { name, strategy, expected_modified: expectedModified || null })
}
