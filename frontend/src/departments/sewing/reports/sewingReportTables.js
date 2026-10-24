/** Presentation rows for the Sewing DPR and SCR, laid out as production_api renders them. */

const sizeKey = size => `size:${size}`

function sizeColumns(sizes) {
	return (sizes || []).map(size => ({ key: sizeKey(size), label: size, numeric: true }))
}

function partColumn(isSetItem, setAttribute) {
	return isSetItem ? [{ key: "part", label: setAttribute || "Part" }] : []
}

export function isNegativeBalance(type, value) {
	const label = String(type || "")
	return (label.toLowerCase().includes("balance") || label === "Delivered - Input") && Number(value) < 0
}

export function scrColourKeys(data, selected = []) {
	return (data.colours || Object.keys(data.data || {}))
		.filter(key => data.data?.[key] && (!selected.length || selected.includes(key)))
}

export function scrColumns(data) {
	return [
		{ key: "colour", label: "Colour", wrap: true },
		...partColumn(data.is_set_item, data.set_attr),
		{ key: "type", label: "Type" },
		...sizeColumns(data.primary_values),
		{ key: "total", label: "Total", numeric: true },
	]
}

/** One row per Type and colour; a set item's parts are separate colour rows. */
export function scrRows(data, selected = []) {
	const keys = scrColourKeys(data, selected)
	return (data.headers || []).flatMap(type => keys.map(key => {
		const group = data.data[key]
		const row = { key: `${type}|${key}`, type, colour: key, part: group.part || "", total: group.type_wise_total?.[type] ?? 0 }
		for (const size of data.primary_values || []) row[sizeKey(size)] = group.values?.[size]?.[type] ?? 0
		return row
	}))
}

function lineNumber(name) {
	const match = String(name).match(/\d+/)
	return match ? Number(match[0]) : Number.MAX_SAFE_INTEGER
}

export function scrLines(data, selected = []) {
	const lines = new Set(scrColourKeys(data, selected).flatMap(key => data.data[key].lines || []))
	return [...lines].sort((a, b) => lineNumber(a) - lineNumber(b) || String(a).localeCompare(String(b)))
}

function dprTable(lot, group) {
	const rows = []
	for (const [station, types] of Object.entries(group.details || {})) {
		for (const [type, colours] of Object.entries(types)) {
			for (const colour of Object.values(colours)) {
				const row = { key: `${station}|${type}|${colour.colour}`, index: rows.length + 1, lot, item: group.item, colour: String(colour.colour).split("@")[0], station, type, part: colour.part || "", remarks: "", total: colour.total }
				for (const [size, value] of Object.entries(colour.values || {})) row[sizeKey(size)] = value
				rows.push(row)
			}
		}
	}
	const columns = [
		{ key: "index", label: "#", numeric: true }, { key: "lot", label: "Lot" }, { key: "item", label: "Item", wrap: true },
		{ key: "colour", label: "Colour", wrap: true }, { key: "station", label: "Line" }, { key: "type", label: "Type" },
		...partColumn(group.is_set_item, group.set_attr), ...sizeColumns(group.primary_values),
		{ key: "remarks", label: "Remarks" }, { key: "total", label: "Total", numeric: true },
	]
	return { lot, columns, rows }
}

/** One section per date and Input Type, each with its Total Qty and one table per Lot. */
export function dprSections(reports) {
	return (reports || []).flatMap(report => (report.headers || [])
		.filter(stage => Object.keys(report.dpr_data?.[stage] || {}).length)
		.map(stage => {
			const tables = Object.entries(report.dpr_data[stage]).map(([lot, group]) => dprTable(lot, group))
			const total = tables.reduce((sum, table) => sum + table.rows.reduce((rowSum, row) => rowSum + Number(row.total || 0), 0), 0)
			return { key: `${report.date}|${stage}`, date: report.date, stage, total, tables }
		}))
}
