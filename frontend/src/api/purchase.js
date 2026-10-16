import { callMethod } from "./frappe.js"

const CAPABILITIES_METHOD = "essdee_yrp.purchase.web_capabilities"
const LOT_METHOD = "essdee_yrp.purchase.lot_workspace"
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

export function searchItemEditorLinks(doctype, text = "", key = null) {
	return callMethod("essdee_yrp.purchase.item_tables.search_item_editor_links", { doctype, txt: text, key })
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

export function setItemDisabled(name, disabled, expectedModified) {
	return callMethod(`${ITEM_METHOD}.set_item_disabled`, {
		name,
		disabled,
		expected_modified: expectedModified,
	})
}

export function getItemPriceWorkspace(name) {
	return callMethod(`${ITEM_PRICE_METHOD}.get_item_price_workspace`, { name })
}

export function getItemPriceSummaries(names) {
	return callMethod(`${ITEM_PRICE_METHOD}.get_item_price_summaries`, { names })
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

export function getLotWorkspace(name) {
	return callMethod(`${LOT_METHOD}.get_lot_workspace`, { name })
}

export function getLotForm(name = null) {
	return callMethod("essdee_yrp.purchase.lot_editor.get_lot_form", { name })
}

export function getLotProductionDetailContext(productionDetail, item, productionOrder = null) {
	return callMethod("essdee_yrp.purchase.lot_editor.get_lot_production_detail_context", {
		production_detail: productionDetail, item, production_order: productionOrder,
	})
}

export function getLotProductionOrderItem(productionOrder) {
	return callMethod("essdee_yrp.purchase.lot_editor.get_lot_production_order_item", {
		production_order: productionOrder,
	})
}

export function saveLot(values, { name, expectedModified }) {
	return callMethod("essdee_yrp.purchase.lot_editor.save_lot", {
		values, name: name || null, expected_modified: expectedModified || null,
	})
}

export function getLotDocuments(lot) {
	return callMethod("essdee_yrp.purchase.lot_documents.get_lot_documents", { lot })
}

export function getLotDocument(lot, doctype, name) {
	return callMethod("essdee_yrp.purchase.lot_documents.get_lot_document", { lot, doctype, name })
}
