const NUMERIC_FIELDTYPES = new Set(["Currency", "Float", "Int", "Percent"])
const LINKED_NAME_LIMIT = 5_000
export const MAX_LINKED_COLUMNS = 20

export function normalizeReportColumn(column, index = 0) {
	if (typeof column === "string") return normalizeStringColumn(column, index)
	const fieldname = column?.fieldname || `column_${index}`
	return {
		...column,
		key: `base:${fieldname}`,
		column_key: `base:${fieldname}`,
		kind: "base",
		fieldname,
		label: column?.label || fieldname,
		fieldtype: column?.fieldtype || "Data",
		align: validAlign(column?.align),
		visible: column?.visible === undefined ? true : Boolean(column.visible),
		width: columnWidth(column?.width),
	}
}

export function reconcileReportLayout(columns, layout, fieldsBySource = {}) {
	const baseColumns = (columns || []).map(normalizeReportColumn)
	if (!Array.isArray(layout)) return baseColumns
	const baseByKey = new Map(baseColumns.map((column) => [column.key, column]))
	const result = []
	const seen = new Set()
	for (const saved of layout) {
		const column = reconcileSavedColumn(saved, baseByKey, fieldsBySource)
		if (!column || seen.has(column.key)) continue
		seen.add(column.key)
		result.push(column)
	}
	for (const column of baseColumns) {
		if (!seen.has(column.key)) result.push(column)
	}
	return result
}

export function cellAlign(column) {
	const align = validAlign(column?.align)
	if (align !== "auto") return `report-align-${align}`
	return NUMERIC_FIELDTYPES.has(column?.fieldtype)
		? "report-align-right"
		: "report-align-left"
}

export function normalizeReportRows(rows, columns) {
	if (!Array.isArray(rows)) return []
	const normalizedColumns = (columns || []).map(normalizeReportColumn)
	return rows.map((row) => {
		if (!Array.isArray(row)) return row
		const result = { is_total_row: true }
		normalizedColumns.forEach((column, index) => {
			result[column.fieldname] = row[index]
		})
		return result
	})
}

export function buildLinkedValueBatches(rows, columns) {
	const fieldsBySource = linkedFieldsBySource(columns)
	const batches = []
	for (const [source, fields] of fieldsBySource) {
		const names = distinctSourceNames(rows, source)
		for (let start = 0; start < names.length; start += LINKED_NAME_LIMIT) {
			batches.push([{
				source_column: source,
				fields: [...fields],
				names: names.slice(start, start + LINKED_NAME_LIMIT),
			}])
		}
	}
	return batches
}

export async function hydrateLinkedValueBatches(batches, fetchBatch, isCurrent) {
	const values = {}
	for (const requests of batches) {
		const response = await fetchBatch(requests)
		if (!isCurrent()) return null
		mergeLinkedValues(values, response || {})
	}
	return values
}

export function createHydrationLifecycle() {
	let generation = 0
	let controller = null

	function invalidate() {
		generation += 1
		controller?.abort()
		controller = null
	}

	function begin() {
		invalidate()
		controller = typeof AbortController === "undefined" ? null : new AbortController()
		const requestGeneration = generation
		return {
			isCurrent: () => requestGeneration === generation,
			signal: controller?.signal,
		}
	}

	return { begin, invalidate }
}

export function reportCellValue(row, column, linkedValues = {}) {
	if (row?.is_total_row && column?.kind === "linked") return ""
	if (column?.kind !== "linked") return row?.[column?.fieldname]
	const rowValue = row?.__linked?.[column.source_column]?.[column.target_field]
	if (rowValue !== undefined) return rowValue
	return linkedValues?.[column.source_column]?.[row?.[column.source_column]]?.[column.target_field] ?? ""
}

export function toLayoutColumn(column) {
	return {
		column_key: column.key,
		kind: column.kind,
		source_column: column.source_column || "",
		target_field: column.target_field || "",
		visible: column.visible ? 1 : 0,
		align: validAlign(column.align),
		width: columnWidth(column.width),
	}
}

export function getLayoutColumnsForSave(columns) {
	const persistableColumns = (columns || []).filter((column) => (
		column.kind !== "linked" || column.visible
	))
	const linkedColumnCount = persistableColumns.filter((column) => column.kind === "linked").length
	if (linkedColumnCount > MAX_LINKED_COLUMNS) {
		throw new Error(`You can select up to ${MAX_LINKED_COLUMNS} linked fields.`)
	}
	return persistableColumns.map(toLayoutColumn)
}

export function linkSourceLabel(source = {}) {
	const doctype = source.doctype || "Linked document"
	return source.label && source.label !== doctype ? `${doctype} (${source.label})` : doctype
}

function reconcileSavedColumn(saved, baseByKey, fieldsBySource) {
	const key = saved?.column_key
	if (saved?.kind === "base" && baseByKey.has(key)) {
		return applySavedSettings(baseByKey.get(key), saved)
	}
	if (saved?.kind !== "linked" || !saved.source_column || !saved.target_field) return null
	const field = (fieldsBySource[saved.source_column] || [])
		.find((candidate) => candidate.fieldname === saved.target_field)
	return applySavedSettings({
		...field,
		key,
		column_key: key,
		kind: "linked",
		fieldname: saved.target_field,
		source_column: saved.source_column,
		target_field: saved.target_field,
		label: linkedLabel(saved.source_column, field?.label || saved.target_field, baseByKey),
		fieldtype: field?.fieldtype || "Data",
		options: field?.options || "",
	}, saved)
}

function applySavedSettings(column, saved) {
	return {
		...column,
		align: validAlign(saved.align),
		visible: saved.visible === undefined ? true : Boolean(saved.visible),
		width: columnWidth(saved.width ?? column.width),
	}
}

function linkedLabel(source, targetLabel, baseByKey) {
	const sourceLabel = baseByKey.get(`base:${source}`)?.label
		|| source.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
	return `${sourceLabel} · ${targetLabel}`
}

function linkedFieldsBySource(columns) {
	const grouped = new Map()
	for (const column of columns || []) {
		if (column.kind !== "linked" || !column.visible) continue
		if (!grouped.has(column.source_column)) grouped.set(column.source_column, new Set())
		grouped.get(column.source_column).add(column.target_field)
	}
	return grouped
}

function distinctSourceNames(rows, source) {
	return [...new Set((rows || [])
		.filter((row) => !row?.is_total_row)
		.map((row) => row?.[source])
		.filter(Boolean))]
}

function mergeLinkedValues(target, response) {
	for (const [source, names] of Object.entries(response)) {
		target[source] = { ...(target[source] || {}), ...(names || {}) }
	}
}

function normalizeStringColumn(value, index) {
	const [label = "", type = "Data", width] = value.split(":")
	const [fieldtype = "Data", options = ""] = type.split("/")
	const fieldname = scrub(label) || `column_${index}`
	return normalizeReportColumn({ label, fieldname, fieldtype, options, width }, index)
}

function scrub(value) {
	return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "")
}

function validAlign(value) {
	return ["left", "center", "right"].includes(value) ? value : "auto"
}

function columnWidth(value) {
	const parsed = Number.parseInt(value, 10)
	return Math.max(60, Math.min(Number.isFinite(parsed) ? parsed : 120, 600))
}
