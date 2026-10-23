/** Totals, grouping and formatting rules of the Frappe 15 Finishing report pages. */

import { formatDisplayByFieldtype } from "../../../utils/dateFormat.js"

const number = (value) => Number(value) || 0

export const FROZEN_COLUMNS = ["item", "description", "lot", "pieces_per_box"]
const TONED_COLUMNS = new Set(["sewing_diff", "cut_to_finishing_diff", "unaccountable", "cut_to_dispatch_diff", "finishing_inward_to_dispatch_diff"])

export function frozenColumnOffsets(columns, widths) {
	const offsets = {}
	let left = 0
	for (const [index, column] of (columns || []).entries()) {
		if (column.kind !== "base" || !FROZEN_COLUMNS.includes(column.fieldname)) continue
		offsets[column.key] = left
		left += Number(widths[index]) || 0
	}
	return offsets
}

export function sumBy(rows, field) {
	return (rows || []).reduce((sum, row) => sum + number(row[field]), 0)
}

export function packedTotals(rows) {
	return { pieces: sumBy(rows, "total_pieces"), boxes: sumBy(rows, "total_boxes") }
}

export function groupByDate(rows, fallbackDate = "") {
	const groups = new Map()
	for (const row of rows || []) {
		const date = row.date || fallbackDate
		if (!groups.has(date)) groups.set(date, [])
		groups.get(date).push(row)
	}
	return [...groups.entries()].map(([date, dateRows]) => ({ date, rows: dateRows }))
}

export function dispatchTotals(rows) {
	const packedBoxes = sumBy(rows, "packed_total_boxes")
	const packedPieces = sumBy(rows, "packed_total_pieces")
	const dispatchedBoxes = sumBy(rows, "dispatched_total_boxes")
	const dispatchedPieces = sumBy(rows, "dispatched_total_pieces")
	return { packedBoxes, packedPieces, dispatchedBoxes, dispatchedPieces, diffBoxes: packedBoxes - dispatchedBoxes, diffPieces: packedPieces - dispatchedPieces }
}

export function dispatchDiff(packed, dispatched) {
	const diff = number(packed) - number(dispatched)
	return diff !== 0 ? diff : ""
}

export function ironingShowsPart(report) {
	const hasPartAttribute = (report?.attributes || []).some((attribute) => String(attribute).toLowerCase() === "part")
	return hasPartAttribute && (report?.rows || []).some((row) => String(row.part || "").trim())
}

function scrub(label) {
	return String(label || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "")
}

export function normalizeReportColumn(column) {
	if (typeof column === "string") {
		const [label = "", type = "Data", width] = column.split(":")
		const [fieldtype = "Data", options = ""] = type.split("/")
		return { label, fieldname: scrub(label), fieldtype: fieldtype || "Data", options, width: Number(width) || 120, align: "auto" }
	}
	return {
		label: column.label || "",
		fieldname: column.fieldname || scrub(column.label),
		fieldtype: column.fieldtype || "Data",
		options: column.options || "",
		width: Number(column.width) || 120,
		align: column.align || "auto",
	}
}

export function formatReportCell(column, row) {
	const value = row?.[column.fieldname]
	if (value === null || value === undefined || value === "") return ""
	if (column.fieldtype === "Percent") return `${Math.round((Number(value) + Number.EPSILON) * 100) / 100}%`
	if (column.fieldtype === "Int") return Number(value).toLocaleString("en-IN", { maximumFractionDigits: 0 })
	if (["Float", "Currency"].includes(column.fieldtype)) return Number(value).toLocaleString("en-IN", { maximumFractionDigits: 3 })
	return String(formatDisplayByFieldtype(value, column.fieldtype))
}

export function reportCellTone(column, row) {
	if (!TONED_COLUMNS.has(column.fieldname)) return ""
	const value = Number(row?.[column.fieldname])
	if (value < 0) return "negative"
	if (value > 0) return "positive"
	return ""
}

export function firstColourLabel(details) {
	return (Object.keys(details || {})[0] || "").split("-").slice(1).join("-")
}
