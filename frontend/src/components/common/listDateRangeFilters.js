/** A Date quick filter's value as `[from, to]`; a single date (from click-to-filter or older saved state) covers that day. */
export function dateRangeValue(value) {
	if (Array.isArray(value)) return [value[0] || "", value[1] || ""]
	return value ? [String(value), String(value)] : ["", ""]
}

export function hasDateRangeValue(value) {
	return dateRangeValue(value).some(Boolean)
}

/** Frappe filters for a Date quick filter: `between` for a range, an open bound otherwise. */
export function dateRangeFilters(fieldname, value) {
	const [from, to] = dateRangeValue(value)
	if (from && to) return [[fieldname, "between", [from, to]]]
	if (from) return [[fieldname, ">=", from]]
	if (to) return [[fieldname, "<=", to]]
	return []
}

/** Today, Yesterday, This Week (Monday start), Last Week, This Month and Last Month as `[from, to]` ranges. */
export function dateRangePresets(today = new Date()) {
	const day = new Date(today.getFullYear(), today.getMonth(), today.getDate())
	const weekStart = shiftDays(day, -((day.getDay() + 6) % 7))
	const monthStart = new Date(day.getFullYear(), day.getMonth(), 1)
	const lastMonthStart = new Date(day.getFullYear(), day.getMonth() - 1, 1)
	return [
		{ label: "Today", value: [isoDate(day), isoDate(day)] },
		{ label: "Yesterday", value: [isoDate(shiftDays(day, -1)), isoDate(shiftDays(day, -1))] },
		{ label: "This Week", value: [isoDate(weekStart), isoDate(shiftDays(weekStart, 6))] },
		{ label: "Last Week", value: [isoDate(shiftDays(weekStart, -7)), isoDate(shiftDays(weekStart, -1))] },
		{ label: "This Month", value: [isoDate(monthStart), isoDate(shiftDays(new Date(day.getFullYear(), day.getMonth() + 1, 1), -1))] },
		{ label: "Last Month", value: [isoDate(lastMonthStart), isoDate(shiftDays(monthStart, -1))] },
	]
}

function shiftDays(date, days) {
	return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days)
}

function isoDate(date) {
	return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
}
