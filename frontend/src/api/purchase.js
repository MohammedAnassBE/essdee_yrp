import { callMethod } from "./frappe.js"

const CAPABILITIES_METHOD = "essdee_yrp.purchase.web_capabilities"
const ITEM_METHOD = "essdee_yrp.purchase.item_editor"
const ITEM_PRICE_METHOD = "essdee_yrp.purchase.item_price_workspace"

export function getPurchaseCapabilities() {
	return callMethod(`${CAPABILITIES_METHOD}.get_capabilities`)
}

export function getItemEditor(name = null) {
	return callMethod(`${ITEM_METHOD}.get_item_editor`, { name })
}

export function searchItemAttributeValues(attribute, text = "", item = null) {
	return callMethod(`${ITEM_METHOD}.search_attribute_values`, { attribute, txt: text, item })
}

export function getItemAttributeCounts(items) {
	return callMethod(`${ITEM_METHOD}.get_item_attribute_counts`, { items })
}

export function createItem(values) {
	return callMethod(`${ITEM_METHOD}.create_item`, { values })
}

export function updateItem(name, values, expectedModified) {
	return callMethod(`${ITEM_METHOD}.update_item`, {
		name,
		values,
		expected_modified: expectedModified,
	})
}

export function getItemPriceWorkspace(name) {
	return callMethod(`${ITEM_PRICE_METHOD}.get_item_price_workspace`, { name })
}

export function getItemPriceEditor(name = null, item = null) {
	return callMethod(`${ITEM_PRICE_METHOD}.get_item_price_editor`, { name, item })
}

export function saveItemPrice(values, options = {}) {
	return callMethod(`${ITEM_PRICE_METHOD}.save_item_price`, {
		values,
		name: options.name || null,
		expected_modified: options.expectedModified ?? null,
	})
}

export function executeItemPriceAction(name, action, expectedModified) {
	return callMethod(`${ITEM_PRICE_METHOD}.execute_item_price_action`, {
		name,
		action,
		expected_modified: expectedModified,
	})
}

export function deleteItemPrice(name, expectedModified) {
	return callMethod(`${ITEM_PRICE_METHOD}.delete_item_price`, {
		name,
		expected_modified: expectedModified,
	})
}
