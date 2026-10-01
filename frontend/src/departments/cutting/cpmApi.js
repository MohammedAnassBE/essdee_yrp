import { callMethod } from "../../api/frappe.js"

const METHOD = "essdee_yrp.cutting.web_workspace."

export function getCpmWorkspace(cuttingPlan) {
	return callMethod(`${METHOD}get_workspace`, { cutting_plan: cuttingPlan })
}

export function getMovementEditor(cuttingPlan, movement = "") {
	return callMethod(`${METHOD}get_movement_editor`, {
		cutting_plan: cuttingPlan,
		movement: movement || undefined,
	})
}

export function generateMovementBundles(cuttingPlan, postingDate = "", postingTime = "") {
	return callMethod(`${METHOD}generate_movement_bundles`, {
		cutting_plan: cuttingPlan,
		posting_date: postingDate || undefined,
		posting_time: postingTime || undefined,
	})
}

export function saveMovement(cuttingPlan, values, movement = "", submit = false, expectedModified = "") {
	return callMethod(`${METHOD}save_movement`, {
		cutting_plan: cuttingPlan,
		values,
		movement: movement || undefined,
		submit,
		expected_modified: expectedModified || undefined,
	})
}

export function changeMovementStatus(cuttingPlan, movement, action) {
	return callMethod(`${METHOD}change_movement_status`, {
		cutting_plan: cuttingPlan,
		movement,
		action,
	})
}

export function getPlanStock(cuttingPlan) {
	return callMethod(`${METHOD}get_plan_stock`, { cutting_plan: cuttingPlan })
}

export function getStockOperationEditor(cuttingPlan, operation) {
	return callMethod(`${METHOD}get_stock_operation_editor`, {
		cutting_plan: cuttingPlan,
		operation,
	})
}

export function getStockItemSchema(cuttingPlan, operation, item) {
	return callMethod(`${METHOD}get_stock_item_schema`, {
		cutting_plan: cuttingPlan,
		operation,
		item,
	})
}

export function saveStockOperation(cuttingPlan, operation, values, submit = false) {
	return callMethod(`${METHOD}save_stock_operation`, {
		cutting_plan: cuttingPlan,
		operation,
		values,
		submit,
	})
}

export function createMovementTransaction(cuttingPlan, movement, operation, values, submit = false) {
	return callMethod(`${METHOD}create_movement_transaction`, {
		cutting_plan: cuttingPlan,
		movement,
		operation,
		values,
		submit,
	})
}

export function getWorkOrderDeliveryEditor(cuttingPlan) {
	return callMethod(`${METHOD}get_work_order_delivery_editor`, {
		cutting_plan: cuttingPlan,
	})
}

export function createWorkOrderDeliveryChallan(cuttingPlan, values, submit = false) {
	return callMethod(`${METHOD}create_work_order_delivery_challan`, {
		cutting_plan: cuttingPlan,
		values,
		submit,
	})
}

export function getLinkedTransaction(cuttingPlan, doctype, name) {
	return callMethod(`${METHOD}get_linked_transaction`, {
		cutting_plan: cuttingPlan,
		doctype,
		name,
	})
}

export function changeLinkedTransactionStatus(cuttingPlan, doctype, name, action) {
	return callMethod(`${METHOD}change_linked_transaction_status`, {
		cutting_plan: cuttingPlan,
		doctype,
		name,
		action,
	})
}
