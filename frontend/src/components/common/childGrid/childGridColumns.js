// Matches GRID_MIN/MAX_COLUMN_WIDTH and LEGACY_COLSIZE_TO_PX in frappe/public/js/frappe/form/grid.js.
export const GRID_MIN_WIDTH = 60
export const GRID_MAX_WIDTH = 600
const LEGACY_COLUMN_WIDTHS = { 1: 60, 2: 100, 3: 140, 4: 200, 5: 250, 6: 300, 7: 350, 8: 400, 9: 450, 10: 500, 11: 550, 12: 600 }
const FIELDTYPE_WIDTHS = {
	Link: 200, "Dynamic Link": 200, Data: 160, Select: 140, Date: 120, Datetime: 170, Time: 110,
	Int: 100, Float: 100, Currency: 110, Percent: 100, Check: 60,
	Text: 220, "Small Text": 220, "Long Text": 240, "Text Editor": 260, Code: 260,
}
const TYPE_WIDTHS = { link: 200, select: 140, value: 160, number: 100, check: 60, text: 140 }
const NUMERIC_FIELDTYPES = new Set(["Int", "Float", "Currency", "Percent"])

export function clampWidth(width) {
	return Math.max(GRID_MIN_WIDTH, Math.min(GRID_MAX_WIDTH, Math.round(Number(width) || 0)))
}

/** Room for an uppercase header label, so fixed columns do not cut short headings. */
export function labelWidth(label) {
	return Math.min(240, Math.round(String(label ?? "").length * 7.5 + 28))
}

export function defaultColumnWidth(column) {
	if (column.width) return clampWidth(column.width)
	return clampWidth(Math.max(FIELDTYPE_WIDTHS[column.fieldtype] || TYPE_WIDTHS[column.type] || 140, labelWidth(column.label)))
}

export function savedEntryWidth(entry) {
	const width = Number.parseInt(entry?.width, 10) || LEGACY_COLUMN_WIDTHS[entry?.columns]
	return width ? clampWidth(width) : null
}

export function isConfigurable(column) {
	return column.configurable !== false
}

function isLocked(column) {
	return Boolean(Number(column.reqd))
}

export const MIN_PERCENT = 3
// Desk renders px widths; /web stores percentages and derives Desk's px from this table width.
export const REFERENCE_WIDTH = 1200

/** Smallest px width a column keeps on narrow screens before the table scrolls sideways. */
export function minColumnWidth(column) {
	return Math.max(GRID_MIN_WIDTH, Math.min(120, Math.round(defaultColumnWidth(column) * 0.6)))
}

/** Whole percentages in proportion to the weights; the last column takes the remainder. */
export function percentsFromWeights(weights) {
	const total = weights.reduce((sum, weight) => sum + Math.max(Number(weight) || 0, 0), 0) || 1
	const percents = weights.slice(0, -1).map((weight) => Math.max(MIN_PERCENT, Math.floor((Math.max(Number(weight) || 0, 0) / total) * 100)))
	return weights.length ? [...percents, 100 - percents.reduce((sum, percent) => sum + percent, 0)] : []
}

function pxPercent(width) {
	return Math.max(MIN_PERCENT, Math.round((width / REFERENCE_WIDTH) * 100))
}

function savedPercent(entry) {
	const percent = Number(entry?.width_percent)
	return Number.isFinite(percent) && percent > 0 ? percent : null
}

/** The previous value when next is structurally equal; a fresh DataTable column list remounts every cell editor. */
export function keepIfUnchanged(previous, next) {
	return previous !== undefined && JSON.stringify(previous) === JSON.stringify(next) ? previous : next
}

/** Visible columns in display order with `percent` (configurable only) and a default px `width`, from the schema plus Frappe GridView entries. */
export function resolveGridColumns(columns, saved) {
	const byKey = new Map(columns.filter(isConfigurable).map((column) => [column.key, column]))
	const entries = (Array.isArray(saved) ? saved : []).filter((entry) => byKey.has(entry?.fieldname))
	const fixed = columns.filter((column) => !isConfigurable(column)).map(withDefaultWidth)
	if (!entries.length) {
		const visible = columns.filter((column) => isConfigurable(column) && !column.hidden).map(withDefaultWidth)
		return [...withPercents(visible, visible.map((column) => column.width)), ...fixed]
	}
	const usePercents = entries.every(savedPercent)
	const chosen = entries.map((entry) => {
		const column = byKey.get(entry.fieldname)
		const width = savedEntryWidth(entry) || defaultColumnWidth(column)
		return { ...column, width: defaultColumnWidth(column), weight: usePercents ? savedPercent(entry) : width }
	})
	const chosenKeys = new Set(chosen.map((column) => column.key))
	const missingLocked = [...byKey.values()].filter((column) => isLocked(column) && !chosenKeys.has(column.key)).map(withDefaultWidth)
		.map((column) => ({ ...column, weight: usePercents ? pxPercent(column.width) : column.width }))
	const visible = [...chosen, ...missingLocked]
	return [...withPercents(visible, visible.map((column) => column.weight)).map(({ weight, ...column }) => column), ...fixed]
}

function withPercents(columns, weights) {
	const percents = percentsFromWeights(weights)
	return columns.map((column, index) => ({ ...column, percent: percents[index] }))
}

function withDefaultWidth(column) {
	return { ...column, width: defaultColumnWidth(column) }
}

/** Px widths for a table this wide: configurable columns share what fixed columns leave, never below their minimum. */
export function layoutWidths(columns, tableWidth, reservedWidth = 0) {
	const fixedWidth = columns.filter((column) => !isConfigurable(column)).reduce((sum, column) => sum + column.width, 0)
	const available = Math.max((tableWidth || REFERENCE_WIDTH) - reservedWidth - fixedWidth, 0)
	const widths = columns.map((column) => isSized(column)
		? Math.max(minColumnWidth(column), Math.floor((available * column.percent) / 100))
		: column.width)
	return shrinkToFit(columns, widths, available)
}

function isSized(column) {
	return isConfigurable(column) && Boolean(column.percent)
}

/** Takes the width that minimums added back from columns above their minimum, so the table still fits. */
function shrinkToFit(columns, widths, available) {
	const slack = columns.map((column, index) => isSized(column) ? widths[index] - minColumnWidth(column) : 0)
	const used = widths.reduce((sum, width, index) => sum + (isSized(columns[index]) ? width : 0), 0)
	const totalSlack = slack.reduce((sum, value) => sum + value, 0)
	if (used <= available || !totalSlack) return widths
	const share = Math.min((used - available) / totalSlack, 1)
	return widths.map((width, index) => width - Math.ceil(slack[index] * share))
}

/** Editable list for the column settings dialog: visible columns first, then hidden ones. */
export function columnDraft(columns, visibleColumns) {
	const visible = visibleColumns.filter(isConfigurable)
	const visibleKeys = new Set(visible.map((column) => column.key))
	const hidden = columns.filter((column) => isConfigurable(column) && !visibleKeys.has(column.key))
	return [
		...visible.map((column) => draftEntry(column, true, column.percent)),
		...hidden.map((column) => draftEntry(column, false, pxPercent(defaultColumnWidth(column)))),
	]
}

function draftEntry(column, visible, percent) {
	return { key: column.key, label: column.label || column.key, visible: visible || isLocked(column), percent, locked: isLocked(column) }
}

/** The last shown column takes 100% minus the others; an error when the others leave it less than MIN_PERCENT. */
export function draftPercents(draft) {
	const shown = draft.filter((column) => column.visible || column.locked)
	const last = shown.at(-1)
	const others = shown.slice(0, -1).reduce((sum, column) => sum + Math.max(Math.round(Number(column.percent) || 0), 0), 0)
	const lastPercent = 100 - others
	const error = last && lastPercent < MIN_PERCENT
		? `Other columns use ${others}%; reduce them to leave room for ${last.label}.`
		: ""
	return { shown, lastKey: last?.key || "", lastPercent, others, error }
}

export function distributeEvenly(draft) {
	const shown = draft.filter((column) => column.visible || column.locked)
	const even = Math.floor(100 / Math.max(shown.length, 1))
	return draft.map((column) => shown.includes(column) ? { ...column, percent: even } : column)
}

/** Frappe Desk GridView rows in display order: px `width` for Desk plus `width_percent` for /web. */
export function gridViewEntries(draft) {
	const { shown, lastKey, lastPercent, error } = draftPercents(draft)
	if (error) throw new Error(error)
	return shown.map((column) => {
		const percent = column.key === lastKey ? lastPercent : Math.max(MIN_PERCENT, Math.round(Number(column.percent) || 0))
		return { fieldname: column.key, width: clampWidth((percent / 100) * REFERENCE_WIDTH), width_percent: percent, sticky: 0 }
	})
}

export function mergeGridView(userSettings, childDoctype, entries) {
	const gridView = { ...(userSettings?.GridView || {}) }
	if (entries?.length) gridView[childDoctype] = entries
	else delete gridView[childDoctype]
	return gridView
}

function isNumericColumn(column) {
	return column.type === "number" || column.type === "check" || NUMERIC_FIELDTYPES.has(column.fieldtype) || column.fieldtype === "Check"
}

function isBlankValue(value) {
	return value === null || value === undefined || (typeof value === "string" && !value.trim()) || (Array.isArray(value) && !value.length)
}

/** A row counts as blank when its text/link columns are empty; defaulted numbers and checks are ignored. */
export function isRowBlank(values, columns) {
	const editable = columns.filter((column) => !column.readonly && column.key)
	const textual = editable.filter((column) => !isNumericColumn(column))
	if (textual.length) return textual.every((column) => isBlankValue(values?.[column.key]))
	return editable.every((column) => isBlankValue(values?.[column.key]) || Number(values[column.key]) === 0)
}

/** What Enter does from a cell: move to the next editable cell, add a row, or nothing. */
export function enterTarget(position, bounds, isEditable, { canAdd = false, rowBlank = true } = {}) {
	for (let index = position.row * bounds.cols + position.col + 1; index < bounds.rows * bounds.cols; index += 1) {
		const cell = { row: Math.floor(index / bounds.cols), col: index % bounds.cols }
		if (isEditable(cell.row, cell.col)) return { action: "move", cell }
	}
	return canAdd && !rowBlank ? { action: "add" } : { action: "none" }
}
