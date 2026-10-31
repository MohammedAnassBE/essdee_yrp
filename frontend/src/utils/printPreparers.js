import { callMethod } from "../api/frappe.js"
import { getProductionOrderPrintDescription, needsProductionOrderPrintDialog, validateProductionOrderPiecesPerBox } from "./productionOrderPrint.js"

/** Per-doctype print preparation: loads settings, asks for a missing value, adds it to the print URL. */
const PRINT_PREPARERS = {
	"YRP Production Order": {
		format: "Essdee Production Order",
		label: "Pieces per Box",
		param: "pieces_per_box",
		load: name => callMethod("essdee_yrp.production_order_workflow.get_production_order_print_settings", { production_order: name }),
		getValue: settings => needsProductionOrderPrintDialog(settings || {}) ? null : Number(settings.pieces_per_box),
		getDescription: settings => getProductionOrderPrintDescription(settings?.fg_item_exists),
		validate: validateProductionOrderPiecesPerBox,
	},
}

export function getPrintPreparer(doctype, format) {
	const preparer = PRINT_PREPARERS[doctype]
	return preparer && preparer.format === format ? preparer : null
}

export function withPrintParam(url, param, value) {
	return `${url}&${new URLSearchParams({ [param]: String(value) })}`
}
