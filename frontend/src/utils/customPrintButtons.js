import { buildPrintUrl } from "./printUrl.js"

export function getCustomPrintButtons(doctype, record = {}, permissions = {}) {
	if (!record?.name) return []
	const buttons = []
	const add = (key, label, format, noLetterhead = true) => buttons.push({ key, label, url: buildPrintUrl({ doctype, name: record.name, format, noLetterhead }) })
	if (doctype === "SD YRP Cutting LaySheet") {
		if (permissions.can_print_movement_chart) add("movement-chart", "Print Movement Chart", String(record.calculated_parts || "").split(",").length > 9 ? "Essdee Cutting Movement Chart 2" : "Essdee Cutting Movement Chart")
		if (permissions.can_print_laysheet) add("laysheet", "Print Laysheet", "Essdee Cutting LaySheet")
		return buttons
	}
	if (!permissions.can_print) return []
	if (doctype === "YRP Production Order" && Number(record.docstatus) === 1) add("production-order", "Print", "Essdee Production Order", null)
	if (doctype === "SD YRP Product") add("tech-pack", "Print Tech Pack", "Essdee Product Tech Pack")
	if (doctype === "SD YRP Product Release") add("tech-pack", "Print Tech Pack", "Essdee Tech Pack")
	if (doctype === "SD YRP Finishing Plan Dispatch" && Number(record.docstatus) === 1) add("dispatch", "Print Dispatch", "Essdee Finishing Plan Dispatch")
	if (doctype === "SD YRP Lot" && record.has_cloth_program) add("cloth-program", "Cloth Program", "Essdee Lot Cloth Program")
	return buttons
}
