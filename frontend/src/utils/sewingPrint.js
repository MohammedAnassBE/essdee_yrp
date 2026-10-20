export function buildSewingConsumptionPrintUrl({ ipd, lot }) {
	const params = new URLSearchParams({
		doctype: "YRP Item Production Detail",
		name: ipd || "",
		format: "Essdee Sewing Consumption",
		no_letterhead: "1",
		lot: lot || "",
		trigger_print: "1",
	})
	return `/printview?${params}`
}

export function buildMonthlySummaryPrintUrl({ supplier, filters = {} }) {
	const params = new URLSearchParams({
		doctype: "Supplier",
		name: supplier || "",
		format: "Essdee Sewing Plan Monthly Summary",
		no_letterhead: "1",
		supplier: supplier || "",
		start_date: filters.fromDate || "",
		end_date: filters.toDate || "",
		trigger_print: "1",
	})
	if (filters.showGrn) params.set("show_grn", "1")
	else params.set("input_type", filters.inputType || "")
	return `/printview?${params}`
}
