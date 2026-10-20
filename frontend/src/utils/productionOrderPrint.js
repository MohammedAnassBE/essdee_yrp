import { buildPrintUrl } from "./printUrl.js"

export function buildProductionOrderPrintUrl({ doctype, name, piecesPerBox }) {
	return buildPrintUrl({ doctype, name, format: "Essdee Production Order", noLetterhead: null }) + "&pieces_per_box=" + encodeURIComponent(piecesPerBox)
}

export function needsProductionOrderPrintDialog(settings) {
	return !(Number(settings.pieces_per_box || 0) > 0)
}

export function getProductionOrderPrintDescription(fgItemExists) {
	return fgItemExists
		? "Pieces per Box is not configured in FG Item Master."
		: "The item is not available in FG Item Master."
}

export function validateProductionOrderPiecesPerBox(value) {
	if (value === null || value === undefined || value === "" || Number(value) === 0) return "Pieces per Box is required."
	if (Number(value) <= 0) return "Pieces per Box must be greater than zero."
	if (!Number.isInteger(Number(value))) return "Pieces per Box must be a whole number greater than zero"
	return ""
}
