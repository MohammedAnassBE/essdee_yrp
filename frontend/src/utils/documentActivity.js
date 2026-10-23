import { formatDisplayByFieldtype } from "./dateFormat.js"

const EMPTY_VALUE = "(empty)"
const EVENT_TEXT = {
	submitted: "submitted this document",
	cancelled: "cancelled this document",
	created: "created this document",
}

/** Unsaved Frappe documents have no name or a local `new-…` name. */
export function isSavedDocumentName(name) {
	const text = String(name ?? "").trim()
	return Boolean(text) && !/^new-/i.test(text)
}

/** Version values in the form's display format: day-first dates, Yes/No checks. */
export function formatActivityValue(value, fieldtype) {
	if (value === null || value === undefined || value === "") return EMPTY_VALUE
	if (fieldtype === "Check") return Number(value) ? "Yes" : "No"
	if (typeof value === "number") return value.toLocaleString("en-IN", { maximumFractionDigits: 6 })
	return String(formatDisplayByFieldtype(value, fieldtype, { fallback: EMPTY_VALUE }))
}

const text = (value) => ({ text: value })
const strong = (value) => ({ text: value, strong: true })
const plural = (count, noun) => `${count} ${noun}${count === 1 ? "" : "s"}`

function changeSegments(change) {
	return [strong(change.label), text(" from "), strong(formatActivityValue(change.old, change.fieldtype)), text(" to "), strong(formatActivityValue(change.new, change.fieldtype))]
}

function joinChanges(changes) {
	return changes.flatMap((change, index) => [...(index ? [text(", ")] : []), ...changeSegments(change)])
}

function eventLines(entry) {
	return (entry.events || []).map((event) => {
		if (event === "amended") return [text("amended this from "), strong(entry.amended_from || "")]
		return [text(EVENT_TEXT[event] || event), ...(entry.via ? [text(" via "), strong(entry.via)] : [])]
	})
}

function rowCountLines(rows, verb, preposition) {
	return (rows || []).map((row) => [text(`${verb} ${plural(row.count, "row")} ${preposition} `), strong(row.table)])
}

/** One Version entry as display lines; each line is a list of `{ text, strong }` segments. */
export function describeActivityEntry(entry) {
	return [
		...eventLines(entry),
		...(entry.changes?.length ? [[text("changed "), ...joinChanges(entry.changes)]] : []),
		...rowCountLines(entry.rows_added, "added", "to"),
		...rowCountLines(entry.rows_removed, "removed", "from"),
		...(entry.row_changes || []).map((row) => [text("changed values for "), strong(row.table), text(` row #${row.row}: `), ...joinChanges(row.changes)]),
	]
}

/** Changes when a reload saved, submitted or cancelled the document; `modified` alone when the record has it. */
export function activityRefreshKey(record) {
	if (!record) return ""
	if (record.modified) return String(record.modified)
	return [record.docstatus, record.status].some((part) => part !== undefined && part !== null && part !== "") ? `${record.docstatus ?? ""}|${record.status ?? ""}` : ""
}
