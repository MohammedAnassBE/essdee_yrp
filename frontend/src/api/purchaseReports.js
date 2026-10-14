import { callMethod } from "./frappe.js"

export function getLotCutQuantity(lots) {
	return callMethod("essdee_yrp.purchase.lot_cut_quantity.get_lot_cut_quantity", { lots })
}
