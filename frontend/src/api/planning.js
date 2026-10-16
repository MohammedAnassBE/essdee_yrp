import { callMethod } from "./frappe.js"

const LOT_METHOD = "essdee_yrp.planning.lot_workspace"
const BULK_CLOSE_METHOD = "essdee_yrp.essdee_yrp.page.work_order_bulk_close.work_order_bulk_close"

export function getOpenWorkOrders(filters) {
	return callMethod(`${BULK_CLOSE_METHOD}.get_open_work_orders`, filters)
}

export function getWorkOrderCloseDetails(workOrder) {
	return callMethod(`${BULK_CLOSE_METHOD}.get_work_order_close_details`, { work_order: workOrder })
}

export function closeWorkOrders(workOrders, values) {
	return callMethod(`${BULK_CLOSE_METHOD}.close_work_orders`, { work_orders: workOrders, ...values })
}

export function getPlanningCapabilities() {
	return callMethod("essdee_yrp.planning.web_workspace.get_capabilities")
}

export function getLotWorkspace(name) {
	return callMethod(`${LOT_METHOD}.get_lot_workspace`, { name })
}

export function getLotDocuments(lot) {
	return callMethod(`${LOT_METHOD}.get_lot_documents`, { lot })
}

export function getLotDocument(lot, doctype, name) {
	return callMethod(`${LOT_METHOD}.get_lot_document`, { lot, doctype, name })
}

export function getLotForm(name = null) {
	return callMethod(`${LOT_METHOD}.get_lot_form`, { name })
}

export function getLotProductionDetailContext(productionDetail, item, productionOrder = null) {
	return callMethod(`${LOT_METHOD}.get_lot_production_detail_context`, {
		production_detail: productionDetail, item, production_order: productionOrder,
	})
}

export function getLotProductionOrderItem(productionOrder) {
	return callMethod(`${LOT_METHOD}.get_lot_production_order_item`, {
		production_order: productionOrder,
	})
}

export function saveLot(values, { name, expectedModified }) {
	return callMethod(`${LOT_METHOD}.save_lot`, {
		values, name: name || null, expected_modified: expectedModified || null,
	})
}
