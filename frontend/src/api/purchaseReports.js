import { callMethod } from "./frappe.js"

export function getPurchaseOrderItemwiseReport(filters) {
	return callMethod("frappe.desk.query_report.run", {
		report_name: "SD YRP Purchase Order Itemwise",
		filters: JSON.stringify(filters),
		ignore_prepared_report: true,
		are_default_filters: true,
	})
}

export function getLotCutQuantity(lots) {
	return callMethod("essdee_yrp.purchase.lot_cut_quantity.get_lot_cut_quantity", { lots })
}
