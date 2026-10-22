export const EXPORT_FORMATS = ["Excel", "CSV"]
export const CSV_QUOTING_OPTIONS = [
	{ value: 0, label: "Minimal" },
	{ value: 1, label: "All" },
	{ value: 2, label: "Non-numeric" },
	{ value: 3, label: "None" },
]

export function defaultExportSettings() {
	return { fileFormat: "Excel", csvDelimiter: ",", csvQuoting: 2, csvDecimalSep: ".", includeFilters: false }
}

const unscrub = fieldname => fieldname.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase())

export function appliedFilterLabels(fields, filters = {}) {
	const applied = {}
	const filterFields = fields?.length ? fields : Object.keys(filters || {}).map(fieldname => ({ fieldname, label: unscrub(fieldname) }))
	for (const field of filterFields) {
		if (field.depends_on && !filters?.[field.depends_on]) continue
		const value = filters?.[field.fieldname]
		if (value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length)) continue
		applied[field.label] = field.fieldtype === "Check" ? (Number(value) ? "Yes" : "No") : value
	}
	return applied
}

function exportSettingsArgs(settings, appliedFilters) {
	const includeFilters = Boolean(settings.includeFilters && Object.keys(appliedFilters || {}).length)
	return {
		file_format_type: settings.fileFormat,
		include_filters: includeFilters ? 1 : 0,
		applied_filters: includeFilters ? appliedFilters : {},
		csv_delimiter: settings.csvDelimiter || ",",
		csv_quoting: Number(settings.csvQuoting ?? 2),
		csv_decimal_sep: settings.csvDecimalSep || ".",
	}
}

export function deskExportArgs({ reportKey, filters, columns, appliedFilters }, settings) {
	return {
		report_key: reportKey,
		filters: filters || {},
		columns: (columns || []).map(column => column.kind === "linked"
			? { kind: "linked", source_column: column.source_column, target_field: column.target_field, label: column.label, fieldtype: column.fieldtype, width: column.width }
			: { kind: "base", fieldname: column.fieldname, label: column.label }),
		...exportSettingsArgs(settings, appliedFilters),
	}
}

export function rowsExportArgs({ title, reportKey, doctype, appliedFilters }, rows, settings) {
	return {
		title,
		rows,
		...(reportKey ? { report_key: reportKey } : { doctype }),
		...exportSettingsArgs(settings, appliedFilters),
	}
}

export function cellExportValue(text) {
	const value = String(text ?? "").replace(/\s*\n\s*/g, "\n").replace(/[ \t ]+/g, " ").trim()
	if (/^-?0\d/.test(value)) return value
	if (/^-?(\d{1,3}(,\d{2,3})+|\d+)(\.\d+)?$/.test(value)) return Number(value.replaceAll(",", ""))
	return value
}

function cellText(cell) {
	return cell.dataset?.exportValue ?? cell.textContent ?? ""
}

export function tableGrid(table) {
	const grid = []
	const carried = []
	for (const row of table.rows || []) {
		const line = []
		let column = 0
		const useCarried = (index) => {
			if (!(carried[index] > 0)) return false
			carried[index] -= 1
			line[index] = ""
			return true
		}
		for (const cell of row.cells || []) {
			while (useCarried(column)) column += 1
			const rowSpan = Math.max(1, Number(cell.rowSpan) || 1)
			for (let offset = 0; offset < Math.max(1, Number(cell.colSpan) || 1); offset += 1) {
				line[column] = offset ? "" : cellExportValue(cellText(cell))
				if (rowSpan > 1) carried[column] = rowSpan - 1
				column += 1
			}
		}
		for (let index = column; index < carried.length; index += 1) useCarried(index)
		grid.push(Array.from(line, value => value ?? ""))
	}
	return grid
}

function tableCaption(table, root) {
	if (table.caption?.textContent) return table.caption.textContent.trim()
	for (let node = table.parentElement; node && node !== root; node = node.parentElement) {
		const heading = [...node.children].find(child => /^H[1-4]$/.test(child.tagName))
		if (heading) return heading.textContent.trim()
	}
	return ""
}

export function renderedReportRows(root) {
	const tables = [...(root?.querySelectorAll?.("table") || [])].filter(table => !table.closest?.("[data-export-ignore]"))
	if (tables.length === 1) return tableGrid(tables[0])
	return tables.flatMap((table, index) => {
		const caption = tableCaption(table, root)
		return [...(index ? [[]] : []), ...(caption ? [[caption]] : []), ...tableGrid(table)]
	})
}

function csvCell(value, quoting, delimiter, decimalSep) {
	const isNumber = typeof value === "number"
	const text = isNumber && decimalSep !== "." ? String(value).replace(".", decimalSep) : String(value ?? "")
	const needsQuotes = text.includes(delimiter) || text.includes('"') || /[\r\n]/.test(text)
	const quoted = `"${text.replaceAll('"', '""')}"`
	if (quoting === 1 || (quoting === 2 && !isNumber)) return quoted
	if (quoting === 0 && needsQuotes) return quoted
	return text
}

export function csvPreview(rows, settings) {
	const delimiter = settings.csvDelimiter || ","
	return (rows || []).slice(0, 4)
		.map(row => row.map(value => csvCell(value, Number(settings.csvQuoting ?? 2), delimiter, settings.csvDecimalSep || ".")).join(delimiter))
		.join("\n")
}

export function deskExportSource(reportKey, filters, columns, filterFields = []) {
	return { reportKey, desk: { filters: filters || {}, columns: columns || [] }, appliedFilters: appliedFilterLabels(filterFields, filters || {}) }
}
