const NUMERIC_FIELDTYPES = new Set(["Currency", "Float", "Int", "Percent", "Duration"])

/** Report columns carry `key`; hand-built table columns may only have `fieldname`. */
export const columnKey = column => column.key ?? column.fieldname

/** frappe-datatable's `isNumber`: anything `isNaN` coerces to a number, including "". */
const isNumber = value => !isNaN(value)

/** Parses one column keyword the way frappe-datatable's `guessFilter` does. */
export function guessFilter(keyword = "") {
	if (keyword.length === 0) return null
	let compareString = keyword
	if ([">", "<", "="].includes(compareString[0])) compareString = keyword.slice(1)
	else if (compareString.startsWith("!=")) compareString = keyword.slice(2)

	if (keyword.startsWith(">") && compareString) return { type: "greaterThan", text: compareString.trim() }
	if (keyword.startsWith("<") && compareString) return { type: "lessThan", text: compareString.trim() }
	if (keyword.startsWith("=") && isNumber(compareString)) return { type: "equals", text: Number(compareString.trim()) }
	// frappe-datatable checks containsNumber first, which turns "!=5" into "contains 5"; /web keeps "!=" meaning not-equals.
	if (keyword.startsWith("!=") && compareString && isNumber(compareString)) return { type: "notEquals", text: Number(compareString.trim()) }
	if (isNumber(compareString)) return { type: "containsNumber", text: compareString }
	const range = keyword.split(":")
	if (range.length === 2 && range.every(value => isNumber(value.trim()))) return { type: "range", text: range.map(value => value.trim()) }
	return { type: "contains", text: compareString.toLowerCase() }
}

/** Per-column values a filter compares against, built once per dataset and column. */
export class ColumnFilterValues {
	constructor(rows, column, { cellValue, cellText }) {
		this.raw = rows.map(row => cellValue(row, column))
		this.numbers = this.raw.map(value => parseFloat(value))
		this.rows = rows
		this.column = column
		this.cellText = cellText
	}

	get rawText() {
		this._rawText ??= this.raw.map(value => (isBlank(value) ? "" : String(value)).toLowerCase())
		return this._rawText
	}

	/** Displayed text, built only when a filter first needs it: formatting thousands of numbers is the slow part. */
	get text() {
		this._text ??= this.rows.map((row, index) => isBlank(this.raw[index]) ? "" : String(this.cellText(row, this.column) ?? "").toLowerCase())
		return this._text
	}

	/** frappe-datatable's getCompareValues: the number when the raw value parses, else the formatted text. */
	compareValue(index) {
		return isNaN(this.numbers[index]) ? this.text[index] : this.numbers[index]
	}

	matches(index, filter) {
		const number = this.numbers[index]
		switch (filter.type) {
			case "contains": return !filter.text || this.rawText[index].includes(filter.text) || this.text[index].includes(filter.text)
			case "greaterThan": return this.compareValue(index) > coerce(this.compareValue(index), filter.text)
			case "lessThan": return this.compareValue(index) < coerce(this.compareValue(index), filter.text)
			case "equals": return number === filter.text
			case "notEquals": return number !== filter.text
			case "range": {
				const value = this.compareValue(index)
				return value >= coerce(value, filter.text[0]) && value <= coerce(value, filter.text[1])
			}
			case "containsNumber": return parseFloat(filter.text) === number || this.text[index].includes(filter.text)
			default: return true
		}
	}
}

// JavaScript compares a number with a numeric string as numbers, which is what frappe-datatable relies on.
function coerce(value, keyword) {
	return typeof value === "number" ? Number(keyword) : keyword
}

function isBlank(value) {
	return value === null || value === undefined || value === ""
}

/** Builds column values lazily, so only the filtered columns pay for their strings. */
export function createRowFilter(rows, columns, accessors) {
	const byKey = new Map(columns.map(column => [columnKey(column), column]))
	const cache = new Map()
	const valuesFor = key => {
		if (!cache.has(key)) cache.set(key, new ColumnFilterValues(rows, byKey.get(key), accessors))
		return cache.get(key)
	}
	return {
		rowCount: rows.length,
		hasColumn: key => byKey.has(key),
		/** Indices of rows matching every column keyword, in row order. */
		getMatchingIndices(keywords) {
			const filters = Object.entries(keywords)
				.filter(([key]) => byKey.has(key))
				.map(([key, keyword]) => [valuesFor(key), guessFilter(keyword)])
				.filter(([, filter]) => filter)
			const indices = []
			for (let index = 0; index < rows.length; index += 1) {
				if (filters.every(([values, filter]) => values.matches(index, filter))) indices.push(index)
			}
			return indices
		},
	}
}

/** Splits a trailing Desk total row off the data rows, like query_report.js does before building the DataTable. */
export function splitTotalRow(rows) {
	const last = rows.at(-1)
	if (!last?.is_total_row || rows.slice(0, -1).some(row => row?.is_total_row)) return { dataRows: rows, totalRow: null }
	return { dataRows: rows.slice(0, -1), totalRow: last }
}

const flt = value => parseFloat(value) || 0
const cint = value => parseInt(value, 10) || 0

/** Desk's DataTable footer: frappe.utils.report_column_total over the visible rows, "Total" in the first empty cell. */
export function columnTotal(values, column) {
	if (column.disable_total || !values.length) return null
	if (column.fieldtype === "Percent") return values.reduce((sum, value) => sum + flt(value), 0) / values.length
	if (column.fieldtype === "Int") return values.reduce((sum, value) => sum + cint(value), 0)
	if (NUMERIC_FIELDTYPES.has(column.fieldtype)) return values.reduce((sum, value) => sum + flt(value), 0)
	return values.reduce((sum, value) => typeof value === "number" ? (sum ?? 0) + value : sum, null)
}

export function filteredTotalRow(rows, columns, cellValue, totalRow = {}) {
	const result = { ...totalRow, is_total_row: true }
	columns.forEach((column, index) => {
		const total = columnTotal(rows.map(row => cellValue(row, column)), column)
		// Linked columns live under their key; Desk total rows leave them blank when read.
		result[column.kind === "linked" ? column.key : column.fieldname] = index === 0 && isBlank(total) ? "Total" : total
	})
	return result
}

/** Keeps keywords that still name a column and are not blank. */
export function activeKeywords(keywords, rowFilter) {
	return Object.fromEntries(Object.entries(keywords).filter(([key, keyword]) => rowFilter.hasColumn(key) && String(keyword ?? "").length))
}
