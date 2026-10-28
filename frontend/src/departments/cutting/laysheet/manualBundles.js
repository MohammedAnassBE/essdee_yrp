export function emptyManualRow(sizes = []) {
	return {
		colour: "",
		major_colour: "",
		set_colour: "",
		shade: "",
		quantity: 1,
		multipliers: Object.fromEntries(sizes.map((size) => [size, 0])),
	}
}

export function manualRowsFromSheet(sheet) {
	const sizes = sheet?.sizes || []
	return (sheet?.manual_items || []).map((row) => ({
		...emptyManualRow(sizes),
		...row,
		multipliers: { ...emptyManualRow(sizes).multipliers, ...(row.multipliers || {}) },
	}))
}

export function applySetFieldDefaults(row, fields, isSetItem) {
	const defaults = Object.fromEntries((fields || []).map((field) => [field.fieldname, field.default]))
	row.major_colour = defaults.major_colour || ""
	if (isSetItem) row.set_colour = defaults.set_colour || ""
}

export function validateManualRows(rows, { sizes = [], isSetItem = false } = {}) {
	for (const [index, row] of rows.entries()) {
		const error = validateManualRow(row, sizes, isSetItem)
		if (error) return `Bundle Row ${index + 1}: ${error}`
	}
	return ""
}

function validateManualRow(row, sizes, isSetItem) {
	if (!text(row.colour)) return "Enter Colour"
	if (!text(row.major_colour)) return "Enter Major Colour"
	if (isSetItem && !text(row.set_colour)) return "Enter Set Colour"
	if (!text(row.shade)) return "Enter the Shade"
	if (!(Number(row.quantity) > 0)) return "Quantity should be greater than Zero"
	const multipliers = sizes.map((size) => Number(row.multipliers?.[size] || 0))
	if (multipliers.some((value) => value < 0)) return "Negative Multiplier's are not Accepted"
	if (!multipliers.some((value) => value > 0)) return "Enter the Multiplier for atleast one size"
	return ""
}

export function manualRowsPayload(rows, { sizes = [], isSetItem = false } = {}) {
	return rows.map((row) => ({
		colour: text(row.colour),
		major_colour: text(row.major_colour),
		...(isSetItem ? { set_colour: text(row.set_colour) } : {}),
		shade: text(row.shade),
		quantity: Number(row.quantity || 0),
		multipliers: Object.fromEntries(sizes.map((size) => [size, Number(row.multipliers?.[size] || 0)])),
	}))
}

function text(value) {
	return String(value ?? "").trim()
}
