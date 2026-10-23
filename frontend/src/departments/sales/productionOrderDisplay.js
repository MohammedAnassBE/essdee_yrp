import { formatDisplayByFieldtype, formatDisplayDate } from "../../utils/dateFormat.js"
import { plainTextFromHtml } from "../../utils/documentValues.js"

export function productionOrderFieldDisplay(field) {
	const value = field.value
	if (value === null || value === undefined || value === "") return "—"
	if (field.display_value) return field.display_value
	if (["Date", "Datetime"].includes(field.fieldtype)) return formatDisplayByFieldtype(value, field.fieldtype)
	if (/date$/i.test(field.fieldname) && /^\d{4}-\d{2}-\d{2}/.test(String(value))) return formatDisplayDate(value)
	if (field.fieldname === "skip_box_sticker_print") return Number(value) ? "Yes" : "No"
	return plainTextFromHtml(value)
}
