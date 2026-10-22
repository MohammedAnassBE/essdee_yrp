import { callMethod } from "./frappe.js"

const METHOD = "essdee_yrp.cutting.plan_editor"

export function getCuttingPlanEditor(name = "", lot = "", duplicateFrom = "") {
	return callMethod(`${METHOD}.get_editor`, {
		cutting_plan: name || undefined,
		lot: lot || undefined,
		duplicate_from: duplicateFrom || undefined,
	})
}

export function loadCuttingPlanLot(lot) {
	return callMethod(`${METHOD}.load_lot_items`, { lot })
}

export function saveCuttingPlan(values, { name = "", submit = false, expectedModified = "" } = {}) {
	return callMethod(`${METHOD}.save`, {
		values,
		name: name || undefined,
		submit,
		expected_modified: expectedModified || undefined,
	})
}

export function changeCuttingPlanStatus(name, action, expectedModified = "") {
	return callMethod(`${METHOD}.change_status`, {
		name,
		action,
		expected_modified: expectedModified || undefined,
	})
}
