export function validateWipFilters(filters) {
	const errors = {}
	if (!filters.category && !filters.product_season && !filters.lot?.length && !filters.item?.length) {
		errors.category = "Set at least one filter other than Lot Status."
	}
	if (!["Open", "Closed"].includes(filters.lot_status)) errors.lot_status = "Lot Status is required."
	if (filters.from_date && !filters.to_date) errors.to_date = "To Date is required"
	if (filters.to_date && !filters.from_date) errors.from_date = "From Date is required"
	if (filters.from_date && filters.to_date && filters.from_date > filters.to_date) {
		errors.to_date = "Lot To Date must be on or after Lot From Date."
	}
	return errors
}

export function columnGroups(columns) {
	return columns.reduce((groups, column) => {
		const previous = groups.at(-1)
		if (previous?.label === column.group) previous.span += 1
		else groups.push({ label: column.group || "", span: 1 })
		return groups
	}, [])
}

export function cellText(row, column) {
	if (column.process && row.not_in_ipd?.includes(column.process)) return "not in IPD"
	if (column.stage && !row.is_total_row && row.process_stages?.[column.process] !== column.stage) return ""
	const value = row[column.fieldname]
	if (value == null) return ""
	if (column.fieldtype === "Date") return String(value).slice(0, 10).split("-").reverse().join("-")
	return typeof value === "number" ? value.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : String(value)
}

export function cellTone(row, column) {
	if (!column.is_difference || row.not_in_ipd?.includes(column.process)) return ""
	if (column.stage && !row.is_total_row && row.process_stages?.[column.process] !== column.stage) return ""
	const value = row[column.fieldname]
	return value < 0 ? "wip-negative" : value > 0 ? "wip-positive" : ""
}

export function reportCsv(rows, columns) {
	const escape = (value) => `"${String(value).replaceAll('"', '""')}"`
	const lines = [columns.map((column) => column.label), ...rows.map((row) => columns.map((column) => {
		const value = row[column.fieldname]
		return typeof value === "number" ? value : cellText(row, column)
	}))]
	return "\uFEFF" + lines.map((line) => line.map((value) => escape(/^[=+\-@]/.test(String(value)) && typeof value !== "number" ? `'${value}` : value)).join(",")).join("\r\n")
}
