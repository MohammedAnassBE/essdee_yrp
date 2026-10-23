import { todayIso } from "../../../components/reports/reportUtils.js"

export function workOrderDefaults(today = todayIso()) {
	const [year, month, day] = today.split("-").map(Number)
	const previousMonth = new Date(year, month - 2, 1)
	const lastDay = new Date(year, month - 1, 0).getDate()
	const fromDate = [previousMonth.getFullYear(), String(previousMonth.getMonth() + 1).padStart(2, "0"), String(Math.min(day, lastDay)).padStart(2, "0")].join("-")
	return { based_on: "Date", from_date: fromDate, to_date: today, supplier: "", process_name: "", item: "", lot: "", status: "" }
}

export function workOrderHint(filters) {
	if (filters.based_on !== "Date") return ""
	if (!filters.from_date || !filters.to_date) return "From and To dates are required in Date mode."
	return filters.from_date > filters.to_date ? "From date cannot be after To date." : ""
}

export function workOrderRequest(filters) {
	const values = { ...filters }
	if (values.based_on === "Date") delete values.status
	else { delete values.from_date; delete values.to_date }
	return populatedFilters(values)
}

export function percentageHint(value) {
	return Number.isFinite(value) && value >= 1 && value <= 100 ? "" : "Enter a percentage between 1 and 100."
}

export function pairedDateHint(filters) {
	if (Boolean(filters.from_date) !== Boolean(filters.to_date)) return "Set both From Date and To Date."
	return filters.from_date && filters.to_date && filters.from_date > filters.to_date ? "From date cannot be after To date." : ""
}

export function mergePastedValues(current, text) {
	return [...new Set([...current, ...text.split(/[\n,]/)].map((value) => value.trim()).filter(Boolean))]
}

export function populatedFilters(filters) {
	return Object.fromEntries(Object.entries(filters).filter(([, value]) => Array.isArray(value) ? value.length : value !== "" && value != null))
}

export function quantityHint(filters) {
	return filters.lot && filters.process ? "" : "Lot and Process are required."
}

export function monthWiseHint(filters) {
	return !filters.lot.length && !filters.item.length ? "Select at least one Lot or Item." : pairedDateHint(filters)
}

export function quantityDeepLink(query) {
	return { lot: typeof query.lot === "string" ? query.lot : "", process: typeof query.process === "string" ? query.process : "" }
}

export function addProcess(values, process) {
	return process && !values.includes(process) ? [...values, process] : [...values]
}

export function moveProcess(values, index, direction) {
	const result = [...values]
	const target = index + direction
	if (index >= 0 && index < result.length && target >= 0 && target < result.length) [result[index], result[target]] = [result[target], result[index]]
	return result
}

export function stockHint(filters) {
	return !filters.lot.length && !filters.item.length && !(filters.category || filters.product_category) ? "Select at least one Lot, Item or Category." : pairedDateHint(filters)
}

export function wipHint(filters) {
	return !filters.lot.length && !filters.item.length && !filters.category && !filters.product_season ? "Select at least one Lot, Item, Category or Season." : pairedDateHint(filters)
}

export function progressTotals(rows, columns, cellValue = (row, column) => row[column.fieldname]) {
	const data = rows.filter((row) => !row.is_total_row)
	if (!data.length) return []
	const total = { item: "Total", is_total_row: true }
	for (const column of columns) {
		if (["Float", "Int", "Currency", "Percent"].includes(column.fieldtype)) total[column.kind === "linked" ? column.key : column.fieldname] = data.reduce((sum, row) => sum + (Number(cellValue(row, column)) || 0), 0)
	}
	return [...data, total]
}

export function progressCellValue(row, column, cellValue) {
	return row.is_total_row && column.kind === "linked" ? row[column.key] ?? "" : cellValue(row, column)
}

export function sizeMatrixColumns(columns, row) {
	const identity = columns.filter((column) => column.fieldname === "type")
	const sizes = row.matrix_sizes || columns.filter((column) => column.fieldname.startsWith("size_")).map((column) => column.label)
	return [...identity, ...sizes.map((size) => columns.find((column) => column.fieldname.startsWith("size_") && column.label === String(size))).filter(Boolean), ...columns.filter((column) => column.fieldname === "total")]
}

export function progressCellLink(column, row) {
	const process = row.process_links?.[column.fieldname]
	return !row.is_total_row && row.lot && process ? { path: "/planning/reports", query: { report: "inhouse-quantity", lot: row.lot, process } } : ""
}
