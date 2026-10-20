export function pendingAnnotation(column, row) {
	const field = column.fieldname
	if (row.is_total_row || !(field.startsWith("supplier_") || field === "others") || !row[field]) return null
	const supplier = field === "others" ? "Others" : column.label
	const days = row.supplier_pending_days?.[supplier]
	const date = row.supplier_last_dc_dates?.[supplier]
	return {
		label: days == null ? "No DC" : `${days} ${days === 1 ? "day" : "days"} pending`,
		title: date ? `Last DC: ${date.split("-").reverse().join("-")}` : "No submitted DC found",
	}
}
