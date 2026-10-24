import { normaliseFrappeTime } from "./documentValues.js"

const pad = (value) => String(value).padStart(2, "0")
const MERIDIEM_PATTERN = /\s*([ap])\.?\s*m?\.?$/i

/** Current local time as Frappe "HH:mm:ss". */
export function currentFrappeTime(now = new Date()) {
	return `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
}

/** Whether the site shows 12-hour times (Frappe System Settings `time_format`). */
export function usesTwelveHourClock(boot = globalThis.frappe?.boot) {
	return /a$/i.test(String(boot?.sysdefaults?.time_format || "").trim())
}

/**
 * Parse typed text into Frappe "HH:mm:ss".
 * Returns "" for empty text and null when the text is not a valid time.
 * Accepts "14:30", "1430", "930", "9", "2:30 pm", "2pm", "14.30", "14:30:15" and "now".
 */
export function parseTimeInput(text, now = new Date()) {
	let value = String(text ?? "").trim().toLowerCase()
	if (!value) return ""
	if (value === "n" || value === "now") return currentFrappeTime(now)
	const meridiem = value.match(MERIDIEM_PATTERN)?.[1]
	if (meridiem) value = value.replace(MERIDIEM_PATTERN, "").trim()
	const parts = splitTimeParts(value)
	if (!parts) return null
	let [hours, minutes, seconds] = parts
	if (meridiem) {
		if (hours < 1 || hours > 12) return null
		hours = (hours % 12) + (meridiem === "p" ? 12 : 0)
	}
	if (hours > 23 || minutes > 59 || seconds > 59) return null
	return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`
}

function splitTimeParts(value) {
	if (/^\d{1,2}([:.]\d{1,2}){1,2}$/.test(value)) {
		const [hours, minutes, seconds = 0] = value.split(/[:.]/).map(Number)
		return [hours, minutes, seconds]
	}
	if (!/^\d{1,6}$/.test(value)) return null
	if (value.length <= 2) return [Number(value), 0, 0]
	if (value.length === 5) return null
	const hourDigits = value.length % 2 === 1 ? 1 : 2
	const hours = Number(value.slice(0, hourDigits))
	const minutes = Number(value.slice(hourDigits, hourDigits + 2))
	const seconds = Number(value.slice(hourDigits + 2) || 0)
	return [hours, minutes, seconds]
}

/** Display a Frappe time; seconds show only when they are not zero. */
export function formatTimeDisplay(value, { twelveHour = false } = {}) {
	const normalised = normaliseFrappeTime(value)
	if (!normalised) return ""
	const [hours, minutes, seconds] = normalised.split(":").map(Number)
	const secondsPart = seconds ? `:${pad(seconds)}` : ""
	if (!twelveHour) return `${pad(hours)}:${pad(minutes)}${secondsPart}`
	const hour = hours % 12 || 12
	return `${hour}:${pad(minutes)}${secondsPart} ${hours < 12 ? "AM" : "PM"}`
}

/** Replace the hour or minute of a Frappe time; seconds reset because the picker has no seconds. */
export function setTimePart(value, part, amount) {
	const normalised = normaliseFrappeTime(value) || "00:00:00"
	const [hours, minutes] = normalised.split(":").map(Number)
	if (part === "hour") return `${pad(amount)}:${pad(minutes)}:00`
	return `${pad(hours)}:${pad(amount)}:00`
}
