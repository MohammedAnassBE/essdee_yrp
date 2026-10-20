import { plainTextFromHtml } from "../../utils/documentValues.js"

export function productionOrderFieldDisplay(field) {
	const value = field.value
	if (value === null || value === undefined || value === "") return "—"
	if (field.display_value) return field.display_value
	if ((["Date", "Datetime"].includes(field.fieldtype) || /date$/i.test(field.fieldname)) && /^\d{4}-\d{2}-\d{2}/.test(String(value))) {
		const [year, month, day] = String(value).slice(0, 10).split("-")
		const time = field.fieldtype === "Datetime" ? String(value).match(/[T ](\d{2}:\d{2})/)?.[1] : ""
		return `${day}-${month}-${year}${time ? ` ${time}` : ""}`
	}
	if (field.fieldname === "skip_box_sticker_print") return Number(value) ? "Yes" : "No"
	return plainTextFromHtml(value)
}
