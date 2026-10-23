const ISO_PATTERN = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{1,2}))?)?/
const DISPLAY_PATTERN = /^(\d{2})-(\d{2})-(\d{4})(?:[ T](\d{1,2}):(\d{2})(?::(\d{1,2}))?)?/
const EMBEDDED_ISO_DATE = /(?<![\w-])(\d{4})-(\d{2})-(\d{2})(?![\w-])/g

const pad = (part) => String(part ?? 0).padStart(2, "0")

/** Split a Frappe date/datetime (ISO string, DD-MM-YYYY string or Date) into padded parts. */
export function getDateParts(value) {
	if (value instanceof Date) {
		if (Number.isNaN(value.getTime())) return null
		return {
			year: String(value.getFullYear()), month: pad(value.getMonth() + 1), day: pad(value.getDate()),
			hour: pad(value.getHours()), minute: pad(value.getMinutes()), second: pad(value.getSeconds()), hasTime: true,
		}
	}
	const text = String(value ?? "").trim()
	const iso = text.match(ISO_PATTERN)
	const display = iso ? null : text.match(DISPLAY_PATTERN)
	const match = iso || display
	if (!match) return null
	const [year, month, day] = iso ? [match[1], match[2], match[3]] : [match[3], match[2], match[1]]
	return { year, month, day, hour: pad(match[4]), minute: match[5] || "00", second: pad(match[6]), hasTime: Boolean(match[4]) }
}

/** Display a date as DD-MM-YYYY; unparseable text is returned unchanged, empty values as `fallback`. */
export function formatDisplayDate(value, fallback = "—") {
	if (value === null || value === undefined || value === "") return fallback
	const parts = getDateParts(value)
	if (!parts) return value instanceof Date ? fallback : String(value)
	return `${parts.day}-${parts.month}-${parts.year}`
}

/** Display a datetime as DD-MM-YYYY HH:mm (HH:mm:ss with `seconds`); date-only values show the date. */
export function formatDisplayDatetime(value, { seconds = false, fallback = "—" } = {}) {
	if (value === null || value === undefined || value === "") return fallback
	const parts = getDateParts(value)
	if (!parts) return value instanceof Date ? fallback : String(value)
	const date = `${parts.day}-${parts.month}-${parts.year}`
	if (!parts.hasTime) return date
	return `${date} ${parts.hour}:${parts.minute}${seconds ? `:${parts.second}` : ""}`
}

/** Display by Frappe fieldtype: Date and Datetime are formatted, anything else is returned as-is. */
export function formatDisplayByFieldtype(value, fieldtype, options = {}) {
	if (fieldtype === "Date") return formatDisplayDate(value, options.fallback)
	if (fieldtype === "Datetime") return formatDisplayDatetime(value, options)
	return value
}

/** Rewrite ISO dates embedded in free text (titles, server messages) as DD-MM-YYYY. */
export function formatDatesInText(text) {
	if (text === null || text === undefined) return text
	return String(text).replace(EMBEDDED_ISO_DATE, (_, year, month, day) => `${day}-${month}-${year}`)
}
