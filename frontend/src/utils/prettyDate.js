import { formatDisplayDatetime, getDateParts } from "./dateFormat.js"

const DATETIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{1,2}))?)?/
const DAY = 86400000

function parseFrappeDatetime(value) {
	const match = String(value || "").match(DATETIME_PATTERN)
	if (!match) return null
	const [, year, month, day, hour = 0, minute = 0, second = 0] = match.map((part) => part && Number(part))
	return new Date(year, month - 1, day, hour, minute, second)
}

function shortLabel(seconds, days) {
	if (days === 0) {
		if (seconds < 60) return "now"
		if (seconds < 3600) return `${Math.floor(seconds / 60)} m`
		return `${Math.floor(seconds / 3600)} h`
	}
	if (days < 7) return `${days} d`
	if (days < 31) return `${Math.floor(days / 7)} w`
	if (days < 365) return `${Math.floor(days / 30)} M`
	return `${Math.floor(days / 365)} y`
}

function plural(count, unit) {
	return count === 1 ? `1 ${unit} ago` : `${count} ${unit}s ago`
}

function longLabel(seconds, days) {
	if (days === 0) {
		if (seconds < 60) return "just now"
		if (seconds < 3600) return plural(Math.floor(seconds / 60), "minute")
		return plural(Math.floor(seconds / 3600), "hour")
	}
	if (days === 1) return "yesterday"
	if (days < 7) return plural(days, "day")
	if (days < 31) return plural(Math.floor(days / 7), "week")
	if (days < 365) return plural(Math.max(1, Math.floor(days / 30)), "month")
	return plural(Math.floor(days / 365), "year")
}

/** Frappe Desk `prettyDate`: "5 m", "2 h", "1 d" (mini) or "5 minutes ago". */
export function prettyDate(value, { now = new Date(), mini = true } = {}) {
	const date = parseFrappeDatetime(value)
	if (!date) return ""
	const seconds = (now.getTime() - date.getTime()) / 1000
	const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
	const eventDay = new Date(date.getFullYear(), date.getMonth(), date.getDate())
	const days = Math.round((today - eventDay) / DAY)
	if (!Number.isFinite(days) || days < 0 || seconds < 0) return ""
	return mini ? shortLabel(seconds, days) : longLabel(seconds, days)
}

/** Server datetime as "DD-MM-YYYY HH:MM:SS", the /web day-first format. */
export function formatFullDateTime(value) {
	return getDateParts(value) ? formatDisplayDatetime(value, { seconds: true }) : ""
}
