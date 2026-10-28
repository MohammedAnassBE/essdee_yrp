export const ENTRY_GRID_INVALID_KEY = Symbol("entry-grid-invalid")

export const ENTRY_GRID_TOOLS = ["fillRight", "fillDown", "sameForAll", "paste", "clear"]

const TRUE_VALUES = new Set(["1", "y", "yes", "true", "✓", "x", "on"])
const FALSE_VALUES = new Set(["", "0", "n", "no", "false", "off"])
const ROW_HEADER_MIN_WIDTH = 140
const ROW_HEADER_MAX_WIDTH = 280
const INDEX_MIN_WIDTH = 44

export function parsePastedBlock(text) {
	const source = String(text ?? "").replace(/\r\n?/g, "\n")
	const rows = []
	let row = []
	let cell = ""
	let quoted = false
	for (let index = 0; index < source.length; index += 1) {
		const character = source[index]
		if (quoted) {
			if (character === '"' && source[index + 1] === '"') { cell += '"'; index += 1 }
			else if (character === '"') quoted = false
			else cell += character
		} else if (character === '"' && cell === "") quoted = true
		else if (character === "\t") { row.push(cell); cell = "" }
		else if (character === "\n") { row.push(cell); rows.push(row); row = []; cell = "" }
		else cell += character
	}
	if (cell !== "" || row.length) { row.push(cell); rows.push(row) }
	return rows
}

export function toTsv(matrix) {
	return (matrix || []).map((row) => row.map(tsvCell).join("\t")).join("\n")
}

function tsvCell(value) {
	const text = value === null || value === undefined ? "" : String(value)
	return /["\t\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export function normalizeRange(anchor, focus = anchor) {
	return {
		top: Math.min(anchor.row, focus.row),
		bottom: Math.max(anchor.row, focus.row),
		left: Math.min(anchor.col, focus.col),
		right: Math.max(anchor.col, focus.col),
	}
}

export function rangeSize(range) {
	return { rows: range.bottom - range.top + 1, cols: range.right - range.left + 1 }
}

export function isCellEditable(rows, columns, row, col) {
	return Boolean(rows[row] && columns[col] && !rows[row].readonly && !columns[col].readonly)
}

export function isChoiceColumn(column) {
	return ["select", "value", "link"].includes(column?.type)
}

export function searchOptions(options, query = "") {
	const text = String(query ?? "").toLowerCase()
	return options.map((option) => ({ option, rank: optionRank(option, text) }))
		.filter(({ rank }) => rank < 3)
		.sort((left, right) => left.rank - right.rank || prefixLength(left) - prefixLength(right))
		.map(({ option }) => option)
}

function optionRank(option, query) {
	if (!query) return 2
	const texts = [option.name, option.label].map((value) => String(value ?? "").toLowerCase())
	if (texts.includes(query)) return 0
	if (texts.some((text) => text.startsWith(query))) return 1
	return texts.some((text) => text.includes(query)) ? 2 : 3
}

function prefixLength({ option, rank }) {
	return rank === 1 ? String(option.label ?? option.name).length : 0
}

const STEPS = { up: [-1, 0], down: [1, 0], left: [0, -1], right: [0, 1] }

export function moveCell(position, direction, bounds, isEditable = () => true) {
	if (STEPS[direction]) {
		const [rowStep, colStep] = STEPS[direction]
		return {
			row: clamp(position.row + rowStep, 0, bounds.rows - 1),
			col: clamp(position.col + colStep, 0, bounds.cols - 1),
		}
	}
	return tabCell(position, direction === "previous" ? -1 : 1, bounds, isEditable)
}

function tabCell(position, step, bounds, isEditable) {
	const total = bounds.rows * bounds.cols
	let index = position.row * bounds.cols + position.col
	for (let count = 0; count < total; count += 1) {
		index = (index + step + total) % total
		const cell = { row: Math.floor(index / bounds.cols), col: index % bounds.cols }
		if (isEditable(cell.row, cell.col)) return cell
	}
	return position
}

function clamp(value, minimum, maximum) {
	return Math.max(minimum, Math.min(maximum, value))
}

export function optionValues(column) {
	return (column.options || []).map((option) => typeof option === "object" ? option.value : option)
}

export function coerceCell(column, raw) {
	const text = raw === null || raw === undefined ? "" : String(raw)
	const type = column.type || "text"
	if (type === "number") return coerceNumber(column, text)
	if (type === "check") return coerceCheck(text)
	if (["select", "value", "link"].includes(type)) return coerceOption(column, text)
	return { value: text === "" ? null : text, error: "" }
}

function coerceNumber(column, text) {
	const clean = text.trim().replace(/,/g, "")
	if (clean === "") return { value: null, error: "" }
	const number = Number(clean)
	if (!Number.isFinite(number)) return { value: null, error: `${text.trim()} is not a number.` }
	if (column.min !== undefined && column.min !== null && number < column.min) {
		return { value: null, error: `Enter ${column.min} or more.` }
	}
	const precision = Number.isInteger(column.precision) ? column.precision : null
	return { value: precision === null ? number : Number(number.toFixed(precision)), error: "" }
}

function coerceCheck(text) {
	const clean = text.trim().toLowerCase()
	if (TRUE_VALUES.has(clean)) return { value: 1, error: "" }
	if (FALSE_VALUES.has(clean)) return { value: 0, error: "" }
	return { value: null, error: `${text.trim()} is not Yes or No.` }
}

function coerceOption(column, text) {
	const clean = text.trim()
	if (clean === "") return { value: null, error: "" }
	const options = optionValues(column)
	if (!options.length && column.type === "link") return { value: clean, error: "" }
	const match = options.find((option) => String(option).toLowerCase() === clean.toLowerCase())
	return match === undefined
		? { value: null, error: `${clean} is not one of the allowed values.` }
		: { value: match, error: "" }
}

export function cellValue(model, rowKey, colKey) {
	return model?.[rowKey]?.[colKey] ?? null
}

export function setCells(model, changes) {
	const next = { ...(model || {}) }
	for (const { rowKey, colKey, value } of changes) {
		next[rowKey] = { ...(next[rowKey] || {}), [colKey]: value }
	}
	return next
}

export function fillColumn(model, rows, columns, col, value) {
	const changes = []
	let skipped = 0
	rows.forEach((row, index) => {
		if (!isCellEditable(rows, columns, index, col)) { skipped += 1; return }
		changes.push({ rowKey: row.key, colKey: columns[col].key, value })
	})
	return { model: setCells(model, changes), changes, skipped }
}

export function applyBlock(model, rows, columns, start, block) {
	const changes = []
	const invalid = []
	let skipped = 0
	let readonly = 0
	block.forEach((line, rowOffset) => line.forEach((raw, colOffset) => {
		const row = start.row + rowOffset
		const col = start.col + colOffset
		if (row >= rows.length || col >= columns.length) { skipped += 1; return }
		if (!isCellEditable(rows, columns, row, col)) { readonly += 1; return }
		const { value, error } = coerceCell(columns[col], raw)
		const cell = { rowKey: rows[row].key, colKey: columns[col].key }
		if (error) invalid.push({ ...cell, value: raw, message: error })
		else changes.push({ ...cell, value })
	}))
	return { model: setCells(model, changes), applied: changes.length, skipped, readonly, invalid, changes }
}

function editableCells(rows, columns, range, mapper) {
	const changes = []
	for (let row = range.top; row <= range.bottom; row += 1) {
		for (let col = range.left; col <= range.right; col += 1) {
			if (!isCellEditable(rows, columns, row, col)) continue
			const change = mapper(row, col)
			if (change) changes.push({ rowKey: rows[row].key, colKey: columns[col].key, value: change.value })
		}
	}
	return changes
}

export function fillRight(model, rows, columns, range) {
	const sourceCol = range.left === range.right ? range.left - 1 : range.left
	if (sourceCol < 0) return { model, changes: [] }
	const target = { ...range, left: range.left === range.right ? range.left : range.left + 1 }
	const changes = editableCells(rows, columns, target, (row) => ({
		value: cellValue(model, rows[row].key, columns[sourceCol].key),
	}))
	return { model: setCells(model, changes), changes }
}

export function fillDown(model, rows, columns, range) {
	const sourceRow = range.top === range.bottom ? range.top - 1 : range.top
	if (sourceRow < 0) return { model, changes: [] }
	const target = { ...range, top: range.top === range.bottom ? range.top : range.top + 1 }
	const changes = editableCells(rows, columns, target, (_row, col) => ({
		value: cellValue(model, rows[sourceRow].key, columns[col].key),
	}))
	return { model: setCells(model, changes), changes }
}

export function sameForAll(model, rows, columns, range) {
	const changes = []
	for (let col = range.left; col <= range.right; col += 1) {
		const source = columns[col]
		const peers = columns
			.map((column, index) => ({ column, index }))
			.filter(({ column, index }) => index !== col && samePeer(source, column))
		for (let row = range.top; row <= range.bottom; row += 1) {
			const value = cellValue(model, rows[row].key, source.key)
			for (const { index } of peers) {
				if (isCellEditable(rows, columns, row, index)) changes.push({ rowKey: rows[row].key, colKey: columns[index].key, value })
			}
		}
	}
	return { model: setCells(model, changes), changes }
}

function samePeer(source, column) {
	if (source.field || column.field) return source.field === column.field
	return (source.type || "text") === (column.type || "text")
}

export function clearRange(model, rows, columns, range) {
	const changes = editableCells(rows, columns, range, () => ({ value: null }))
	return { model: setCells(model, changes), changes }
}

export function displayCell(column, value) {
	if (value === null || value === undefined || value === "") return ""
	if (column.type === "check") return Number(value) ? "✓" : ""
	if (column.type === "number" && Number.isInteger(column.precision) && typeof value === "number") {
		return value.toLocaleString("en-IN", { maximumFractionDigits: column.precision, useGrouping: false })
	}
	const option = (Array.isArray(column.options) ? column.options : []).find((candidate) => typeof candidate === "object" && candidate.value === value)
	return option ? option.label : String(value)
}

export function rangeMatrix(model, rows, columns, range) {
	const matrix = []
	for (let row = range.top; row <= range.bottom; row += 1) {
		const line = []
		for (let col = range.left; col <= range.right; col += 1) {
			line.push(displayCell(columns[col], cellValue(model, rows[row].key, columns[col].key)))
		}
		matrix.push(line)
	}
	return matrix
}

export function columnTotals(model, rows, columns) {
	return Object.fromEntries(columns.filter((column) => column.type === "number").map((column) => [
		column.key,
		roundTotal(rows.reduce((sum, row) => sum + numeric(cellValue(model, row.key, column.key)), 0)),
	]))
}

export function rowTotal(model, row, columns) {
	return roundTotal(columns.filter((column) => column.type === "number")
		.reduce((sum, column) => sum + numeric(cellValue(model, row.key, column.key)), 0))
}

function numeric(value) {
	const number = Number(value)
	return Number.isFinite(number) ? number : 0
}

function roundTotal(value) {
	return Math.round(value * 10000) / 10000
}

export function pasteReportText(report) {
	const parts = [`Pasted ${report.rows} × ${report.cols}`]
	if (report.skipped) parts.push(`${report.skipped} ${report.skipped === 1 ? "cell" : "cells"} outside the grid skipped`)
	if (report.readonly) parts.push(`${report.readonly} read-only ${report.readonly === 1 ? "cell" : "cells"} skipped`)
	if (report.invalid?.length) parts.push(`${report.invalid.length} ${report.invalid.length === 1 ? "value" : "values"} not allowed`)
	return parts.join(" · ")
}

export function isPrintableKey(event) {
	return event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey
}

export function columnMinWidth(column) {
	if (column.width) return column.width
	if (column.type === "number" || column.type === "check") return 72
	if (column.type === "link") return 180
	return 120
}

/** Row header px width: a "#" index fits its row numbers; a label column fits its labels within 140-280px. */
export function rowHeaderColumnWidth(rows, isIndex = false) {
	const longest = Math.max(0, ...rows.map((row) => String(row.label ?? "").length))
	if (isIndex) return Math.max(INDEX_MIN_WIDTH, longest * 8 + 20)
	return Math.min(ROW_HEADER_MAX_WIDTH, Math.max(ROW_HEADER_MIN_WIDTH, longest * 8 + 28))
}
