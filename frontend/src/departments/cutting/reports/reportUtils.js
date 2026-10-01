export function todayIso() {
	const now = new Date()
	const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
	return local.toISOString().slice(0, 10)
}

export function firstDayOfMonthIso() {
	const now = new Date()
	const local = new Date(now.getFullYear(), now.getMonth(), 1)
	return [local.getFullYear(), String(local.getMonth() + 1).padStart(2, "0"), "01"].join("-")
}

export function oneMonthAgoIso() {
	const now = new Date()
	const local = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate())
	return [
		local.getFullYear(),
		String(local.getMonth() + 1).padStart(2, "0"),
		String(local.getDate()).padStart(2, "0"),
	].join("-")
}

export function formatDate(value) {
	if (!value) return "—"
	const date = String(value).slice(0, 10).split("-")
	return date.length === 3 ? `${date[2]}-${date[1]}-${date[0]}` : String(value)
}

export function number(value, precision = 0) {
	const parsed = Number(value)
	if (!Number.isFinite(parsed)) return precision ? (0).toFixed(precision) : "0"
	return parsed.toLocaleString("en-IN", {
		minimumFractionDigits: precision,
		maximumFractionDigits: precision,
	})
}

export function quantity(value) {
	const parsed = Number(value)
	if (!Number.isFinite(parsed) || parsed === 0) return "—"
	return number(parsed, Number.isInteger(parsed) ? 0 : 2)
}

export function rowColour(row) {
	return row?.attributes?.Colour || row?.item_keys?.major_colour || ""
}

export function attributeValue(row, attribute) {
	const value = row?.attributes?.[attribute]
	if (attribute !== "Colour" || !value) return value || "—"
	const major = row?.item_keys?.major_colour
	const differs = row.is_set_item
		? row.attributes?.[row.set_attr] !== row.major_attr_value
		: value !== major
	return differs && major ? `${value} (${major})` : value
}

export function pending(row) {
	return Number(row?.cumulative || 0) - Number(row?.planned || 0)
}

export function reportRowCount(groups) {
	return (groups || []).reduce((count, group) => count + (group.items?.length || 0), 0)
}

export function errorMessage(error, fallback = "Unable to generate this report.") {
	return error?.message || fallback
}

export function stockCellValue(value, column) {
	if (value === null || value === undefined || value === "") return "—"
	if (column?.fieldtype === "Date") return formatDate(value)
	if (["Float", "Currency", "Int"].includes(column?.fieldtype)) {
		return number(value, column.fieldtype === "Int" ? 0 : 3)
	}
	return String(value)
}
