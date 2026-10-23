import { callMethod, callRead } from "./frappe.js"

const WORKSPACE_METHOD = "essdee_yrp.fabric_store.web_workspace"

export function getFabricStoreCapabilities() {
	return callRead(`${WORKSPACE_METHOD}.get_capabilities`)
}

export function getWorkOrderWorkspace(workOrder) {
	return callMethod(`${WORKSPACE_METHOD}.get_work_order_workspace`, { work_order: workOrder })
}

export function getWorkOrderEditor(workOrder = "", source = {}) {
	return callMethod(`${WORKSPACE_METHOD}.get_work_order_editor`, {
		name: workOrder || undefined,
		source: Object.keys(source || {}).length ? source : undefined,
	})
}

export function saveWorkOrder(values, options = {}) {
	return callMethod(`${WORKSPACE_METHOD}.save_work_order_document`, {
		values,
		name: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || undefined,
	})
}

export function executeWorkOrderCommand(name, command, payload = {}, expectedModified = "") {
	return callMethod(`${WORKSPACE_METHOD}.execute_work_order_command`, {
		name,
		command,
		payload,
		expected_modified: expectedModified || undefined,
	})
}

export function getWorkOrderSelectionContext(lot, processName) {
	return callMethod("essdee_yrp.api.work_order.get_work_order_selection_context", {
		lot,
		process_name: processName,
	})
}

export function getWorkOrderFabricCalculationContext(workOrder, sourceProcess = "") {
	return callMethod("essdee_yrp.api.work_order.get_fabric_deliverable_context", {
		work_order: workOrder,
		source_process: sourceProcess || undefined,
	})
}

export function getFabricStoreDocument(doctype, name) {
	return callMethod(`${WORKSPACE_METHOD}.get_document`, { doctype, name })
}

export function getDeliveryChallanWorkspace(name = "", source = {}) {
	return callMethod(`${WORKSPACE_METHOD}.get_delivery_challan_workspace`, {
		name: name || undefined,
		source: Object.keys(source || {}).length ? source : undefined,
	})
}

export function previewDeliveryChallanSource(workOrder, values = {}) {
	return callMethod(`${WORKSPACE_METHOD}.preview_delivery_challan_source`, {
		work_order: workOrder,
		values,
	})
}

export function saveDeliveryChallan(values, options = {}) {
	return callMethod(`${WORKSPACE_METHOD}.save_delivery_challan`, {
		values,
		name: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || undefined,
	})
}

export function executeDeliveryChallanCommand(name, command, payload = {}, expectedModified = "") {
	return callMethod(`${WORKSPACE_METHOD}.execute_delivery_challan_command`, {
		name,
		command,
		payload,
		expected_modified: expectedModified || undefined,
	})
}

export function getGoodsReceivedNoteWorkspace(name = "", source = {}) {
	return callMethod(`${WORKSPACE_METHOD}.get_goods_received_note_workspace`, {
		name: name || undefined,
		source: Object.keys(source || {}).length ? source : undefined,
	})
}

export function previewGoodsReceivedNoteSource(source = {}) {
	return callMethod(`${WORKSPACE_METHOD}.preview_goods_received_note_source`, { source })
}

export function getGoodsReceivedNoteDeliveryAddress(deliveryLocation) {
	return callMethod("essdee_yrp.fabric_store.documents.goods_received_note.get_delivery_address", { delivery_location: deliveryLocation })
}

export function getGoodsReceivedNoteSupplierAddress(supplier) {
	return callMethod("essdee_yrp.fabric_store.documents.goods_received_note.get_supplier_address", { supplier })
}

export function saveGoodsReceivedNote(values, options = {}) {
	return callMethod(`${WORKSPACE_METHOD}.save_goods_received_note`, {
		values,
		name: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || undefined,
	})
}

export function getGoodsReceivedNoteCalculation(name) {
	return callMethod(`${WORKSPACE_METHOD}.get_goods_received_note_calculation`, { name })
}

export function calculateGoodsReceivedNote(name, rows, receivedType, expectedModified = "") {
	return callMethod(`${WORKSPACE_METHOD}.calculate_goods_received_note`, {
		name,
		rows,
		received_type: receivedType,
		expected_modified: expectedModified || undefined,
	})
}

export function saveGoodsReceivedNoteInspection(name, values, options = {}) {
	return callMethod(`${WORKSPACE_METHOD}.save_goods_received_note_inspection`, {
		name,
		values,
		inspection_name: options.inspectionName || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || undefined,
	})
}

export function executeGoodsReceivedNoteCommand(name, command, payload = {}, expectedModified = "") {
	return callMethod(`${WORKSPACE_METHOD}.execute_goods_received_note_command`, {
		name,
		command,
		payload,
		expected_modified: expectedModified || undefined,
	})
}

export function changeFabricStoreDocumentStatus(doctype, name, action, expectedModified = "") {
	return callMethod(`${WORKSPACE_METHOD}.change_document_status`, {
		doctype,
		name,
		action,
		expected_modified: expectedModified || undefined,
	})
}

export function getDeliveryChallanReturnEditor(deliveryChallan) {
	return callMethod(`${WORKSPACE_METHOD}.get_delivery_challan_return_editor`, {
		delivery_challan: deliveryChallan,
	})
}

export function getDeliveryChallanReturnMovement(deliveryChallan, cutPanelMovement) {
	return callMethod(`${WORKSPACE_METHOD}.get_delivery_challan_return_movement`, {
		delivery_challan: deliveryChallan,
		cut_panel_movement: cutPanelMovement,
	})
}

export function getCollapsedStock(lot, location) {
	return callMethod(`${WORKSPACE_METHOD}.get_collapsed_stock`, { lot, location })
}

export function createDeliveryChallanReturn(deliveryChallan, items, receivedType = "") {
	return callMethod(`${WORKSPACE_METHOD}.create_delivery_challan_return`, {
		delivery_challan: deliveryChallan,
		items,
		received_type: receivedType || undefined,
	})
}

export function completeWorkOrderDocumentTransfer(doctype, name) {
	return callMethod(`${WORKSPACE_METHOD}.complete_work_order_document_transfer`, { doctype, name })
}

export function getPurchaseOrderWorkspace(purchaseOrder) {
	return callMethod(`${WORKSPACE_METHOD}.get_purchase_order_workspace`, { purchase_order: purchaseOrder })
}

export function getPurchaseOrderEditor(purchaseOrder = "", source = {}) {
	return callMethod(`${WORKSPACE_METHOD}.get_purchase_order_editor`, {
		purchase_order: purchaseOrder || undefined,
		source: Object.keys(source || {}).length ? source : undefined,
	})
}

export function getPurchaseOrderItemSchema(item, purchaseOrder = "") {
	return callMethod(`${WORKSPACE_METHOD}.get_purchase_order_item_schema`, {
		item,
		purchase_order: purchaseOrder || undefined,
	})
}

export function searchPurchaseOrderAdditionalParameterValues(item, parameterKey, txt = "", purchaseOrder = "") {
	return callMethod(`${WORKSPACE_METHOD}.search_purchase_order_additional_parameter_values`, {
		item,
		parameter_key: parameterKey,
		txt,
		purchase_order: purchaseOrder || undefined,
	})
}

export function getPurchaseOrderItemPrice(itemDetail, supplier, purchaseOrder = "") {
	return callMethod(`${WORKSPACE_METHOD}.get_purchase_order_item_price`, {
		item_detail: itemDetail,
		supplier,
		purchase_order: purchaseOrder || undefined,
	})
}

export function previewPurchaseOrderPrices(items, supplier, purchaseOrder = "") {
	return callMethod(`${WORKSPACE_METHOD}.preview_purchase_order_prices`, {
		items,
		supplier,
		purchase_order: purchaseOrder || undefined,
	})
}

export function savePurchaseOrder(values, options = {}) {
	return callMethod(`${WORKSPACE_METHOD}.save_purchase_order`, {
		values,
		purchase_order: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || undefined,
	})
}

export function executePurchaseOrderCommand(name, command, payload = {}, expectedModified = "") {
	return callMethod(`${WORKSPACE_METHOD}.execute_purchase_order_command`, {
		purchase_order: name,
		command,
		payload,
		expected_modified: expectedModified || undefined,
	})
}

export function getFabricStockOperationEditor(operation, options = {}) {
	return callMethod(`${WORKSPACE_METHOD}.get_stock_operation_editor`, { operation, name: options.name || undefined, source_context: options.sourceContext || undefined })
}

export function getFabricStockItemSchema(operation, item) {
	return callMethod(`${WORKSPACE_METHOD}.get_stock_item_schema`, { operation, item })
}

export function getStockUpdateRates(row, warehouse) {
	return callMethod("yrp.yrp_stock.doctype.yrp_stock_update.yrp_stock_update.get_stock_update_rates", {
		item: row.name,
		attributes: row.attributes || {},
		primary_attribute: row.primary_attribute || "",
		value_keys: Object.keys(row.values || {}),
		warehouse,
		dimensions: row.dimensions || {},
	})
}

export function saveFabricStockOperation(operation, values, options = {}) {
	return callMethod(`${WORKSPACE_METHOD}.save_stock_operation`, {
		operation,
		values,
		name: options.name || undefined,
		submit: Boolean(options.submit),
		expected_modified: options.expectedModified || undefined,
	})
}

export function discardCompletionDraft(name, expectedModified = "") {
	return callMethod(`${WORKSPACE_METHOD}.discard_completion_draft`, { name, expected_modified: expectedModified || undefined })
}

export function getLocationAddressStatus(party) {
	return callMethod(`${WORKSPACE_METHOD}.get_location_address_status`, { party })
}

export function endStockEntryTransit(name) {
	return callMethod(`${WORKSPACE_METHOD}.end_stock_entry_transit`, { name })
}
