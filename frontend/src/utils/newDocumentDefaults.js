const SKIPPED_FIELDTYPES = new Set([
	"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Heading", "Fold", "Image",
	"Table", "Table MultiSelect", "Attachment Gallery",
])
const SKIPPED_FIELDNAMES = new Set(["name", "docstatus", "owner", "creation", "modified", "modified_by", "idx", "amended_from", "workflow_state"])

let staged = null

function isEmptyValue(value) {
	return value === null || value === undefined || value === ""
}

function isDefaultableField(field) {
	return Boolean(field?.fieldname && !SKIPPED_FIELDNAMES.has(field.fieldname) && !SKIPPED_FIELDTYPES.has(field.fieldtype)
		&& !Number(field.read_only) && !Number(field.is_virtual))
}

/** Values a new `doctype` document takes from the list's `field = value` filters, as Desk's route_options do. */
export function equalityFilterDefaults(filters, doctype, fields, { excludedFieldnames = [] } = {}) {
	const byName = new Map((fields || []).map((field) => [field.fieldname, field]))
	const excluded = new Set(excludedFieldnames)
	const values = {}
	for (const filter of filters || []) {
		if (!Array.isArray(filter)) continue
		const [filterDoctype, fieldname, operator, value] = filter.length >= 4 ? filter : [doctype, ...filter]
		const field = byName.get(fieldname)
		if (filterDoctype !== doctype || operator !== "=" || isEmptyValue(value) || excluded.has(fieldname) || !isDefaultableField(field)) continue
		values[fieldname] = field.fieldtype === "Check" ? Number(value) : value
	}
	return values
}

/** Holds `values` for the next new `doctype` form opened from the list at `sourcePath`. */
export function stageNewDocumentDefaults(doctype, values, sourcePath) {
	staged = Object.keys(values || {}).length ? { doctype, values: { ...values }, sourcePath } : null
}

/** One-shot staged defaults for a new `doctype`, given only to a form opened from or over the staging list. */
export function takeNewDocumentDefaults(doctype, historyState = globalThis.window?.history?.state) {
	if (!staged || staged.doctype !== doctype) return {}
	const entry = staged
	staged = null
	return [historyState?.back, historyState?.current].includes(entry.sourcePath) ? { ...entry.values } : {}
}

/** `record` with each default filled into a field the form left empty (or an unticked Check); computed values win. */
export function withNewDocumentDefaults(record, defaults) {
	const next = { ...(record || {}) }
	for (const [fieldname, value] of Object.entries(defaults || {})) {
		const current = next[fieldname]
		if (isEmptyValue(current) || (value === 1 && Number(current) === 0)) next[fieldname] = value
	}
	return next
}
