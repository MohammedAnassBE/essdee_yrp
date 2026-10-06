import { callMethod } from "./frappe.js"

const ORDER_METHOD = "essdee_yrp.cutting.order_workspace"
const DETAIL_METHOD = "essdee_yrp.cutting.order_detail_editor"

export function getCuttingOrderEditor(name = "", detail = "") {
	return callMethod(`${ORDER_METHOD}.get_order_editor`, {
		cutting_order: name || undefined,
		cutting_order_detail: detail || undefined,
	})
}

export function saveCuttingOrder(values, { name = "", submit = false, expectedModified = "" } = {}) {
	return callMethod(`${ORDER_METHOD}.save_order`, {
		values,
		name: name || undefined,
		submit,
		expected_modified: expectedModified || undefined,
	})
}

export function changeCuttingOrderStatus(name, action, expectedModified = "") {
	return callMethod(`${ORDER_METHOD}.change_order_status`, {
		name,
		action,
		expected_modified: expectedModified || undefined,
	})
}

export function getCuttingOrderWorkspace(name) {
	return callMethod(`${ORDER_METHOD}.get_order_workspace`, { cutting_order: name })
}

export function updateCuttingOrderCompleted(name, completedItems, expectedModified = "") {
	return callMethod(`${ORDER_METHOD}.update_completed_items`, {
		cutting_order: name,
		completed_items: completedItems,
		expected_modified: expectedModified || undefined,
	})
}

export function getCuttingOrderDetail(name = "", item = "") {
	return callMethod(`${DETAIL_METHOD}.get_detail_editor`, {
		name: name || undefined,
		item: item || undefined,
	})
}

export function saveCuttingOrderDetail(values, { name = "", expectedModified = "" } = {}) {
	return callMethod(`${DETAIL_METHOD}.save_detail`, {
		values,
		name: name || undefined,
		expected_modified: expectedModified || undefined,
	})
}
