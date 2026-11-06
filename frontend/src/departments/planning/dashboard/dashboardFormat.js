import { formatDisplayDate } from "../../../utils/dateFormat.js"

const integer = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 })
const oneDecimal = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 1 })

/** Indian-grouped whole number, or one decimal when `decimals` is set. */
export function formatQuantity(value, decimals = false) {
	return (decimals ? oneDecimal : integer).format(Number(value || 0))
}

export function plural(count, word) {
	return `${integer.format(count)} ${word}${count === 1 ? "" : "s"}`
}

export function percentOf(part, whole) {
	return whole ? (part / whole) * 100 : 0
}

/** Whole days from `from` to `to` (ISO dates). */
export function daysBetween(from, to) {
	if (!from || !to) return 0
	return Math.round((Date.parse(to) - Date.parse(from)) / 86400000)
}

/** "DD-MM-YYYY" plus the days late against the data date, when late. */
export function deliveryParts(delivery, asOf) {
	const late = daysBetween(delivery, asOf)
	return { date: formatDisplayDate(delivery), lateDays: delivery && late > 0 ? late : 0 }
}

function quote(value) {
	const text = String(value ?? "")
	return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function csvText(lines) {
	return lines.map((line) => line.map(quote).join(",")).join("\n")
}

export function roundQuantity(value) {
	return Math.round(Number(value || 0) * 100) / 100
}
