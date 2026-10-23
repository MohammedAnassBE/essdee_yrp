const CLICK_FILTER_FIELDTYPES = new Set(["Link", "Select", "Data", "Check", "Date"])

/** Whether clicking a cell value filters the list by it; Desk skips the name and numeric columns. */
export function isClickFilterColumn(column, { isStatus = false } = {}) {
	if (!column?.fieldname || column.fieldname === "name") return false
	return isStatus || CLICK_FILTER_FIELDTYPES.has(column.fieldtype)
}

/** The filter value a clicked cell stands for; Check cells match the quick filter's 1/0 values. */
export function clickFilterValue(column, value) {
	return column?.fieldtype === "Check" ? Number(value) : value
}

/** `filters` with any equality filter on the parent field replaced by `fieldname = value`. */
export function replaceEqualityFilter(filters, doctype, fieldname, value) {
	const kept = (filters || []).filter((filter) => !isEqualityFilterOn(filter, doctype, fieldname))
	return [...kept.map((filter) => [...filter]), [fieldname, "=", value]]
}

function isEqualityFilterOn(filter, doctype, fieldname) {
	const [filterDoctype, field, operator] = filter.length >= 4 ? filter : [doctype, ...filter]
	return filterDoctype === doctype && field === fieldname && operator === "="
}
