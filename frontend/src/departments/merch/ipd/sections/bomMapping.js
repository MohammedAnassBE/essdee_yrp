const blank = (value) => value == null || String(value).trim() === ""

export function mappingColumns(itemRows = [], bomRows = []) {
	const itemSame = itemRows.filter((row) => Number(row.same_attribute)).map((row) => row.attribute)
	const same = bomRows.filter((row) => Number(row.same_attribute) && itemSame.includes(row.attribute)).map((row) => row.attribute)
	const item = itemRows.map((row) => row.attribute).filter((attribute) => !same.includes(attribute))
	const bom = bomRows.map((row) => row.attribute).filter((attribute) => !same.includes(attribute))
	return { item, bom, same, all_same: same.length > 0 && item.length === 0 }
}

export function freshGrid(combinations, columns) {
	return combinations.map((combination, index) => ({
		key: String(index), index, included: true,
		item: Object.fromEntries(columns.item.map((attribute) => [attribute, combination[attribute]])),
		bom: Object.fromEntries(columns.bom.map((attribute) => [attribute, null])),
		quantity: 0,
	}))
}

function savedLines(values) {
	const lines = new Map()
	for (const value of values || []) {
		const index = Number(value.index)
		if (!lines.has(index)) lines.set(index, { index, item: {}, bom: {}, quantity: 0 })
		const line = lines.get(index)
		if (value.type === "item" || value.type === "bom") line[value.type][value.attribute] = value.attribute_value
		line.quantity = value.quantity
	}
	return [...lines.values()].sort((left, right) => left.index - right.index)
}

export function gridFromValues(combinations, columns, savedValues) {
	const rows = freshGrid(combinations, columns).map((row) => ({ ...row, included: false }))
	let dropped = 0
	for (const line of savedLines(savedValues)) {
		const row = rows.find((candidate) => columns.item.every((attribute) => candidate.item[attribute] === line.item[attribute]))
		if (!row) { dropped += 1; continue }
		row.included = true
		row.bom = Object.fromEntries(columns.bom.map((attribute) => [attribute, line.bom[attribute] ?? null]))
		row.quantity = line.quantity ?? 0
	}
	return { rows, dropped }
}

function rowProblems(row, columns) {
	const problems = {}
	for (const attribute of columns.item) if (blank(row.item[attribute])) problems[`item:${attribute}`] = "Choose a value"
	for (const attribute of columns.bom) if (blank(row.bom[attribute])) problems[`bom:${attribute}`] = "Choose a value"
	if (!Number.isFinite(Number(row.quantity)) || !Number(row.quantity)) problems.quantity = "Quantity cannot be zero"
	return problems
}

export function mappingOutput(rows, columns) {
	if (columns.all_same) return { values: [], problems: {}, error: "" }
	const values = [], problems = {}
	let firstError = ""
	rows.forEach((row, index) => {
		if (!row.included) return
		const missing = rowProblems(row, columns)
		if (Object.keys(missing).length) problems[row.key] = missing
		if (!firstError && Object.keys(missing).length) {
			const column = Object.keys(missing)[0]
			firstError = `Row ${index + 1}: ${column === "quantity" ? "Quantity cannot be zero" : `choose ${column.slice(column.indexOf(":") + 1)}`}.`
		}
		for (const type of ["item", "bom"]) {
			for (const attribute of columns[type]) {
				values.push({ index, type, attribute, attribute_value: row[type][attribute], quantity: Number(row.quantity) })
			}
		}
	})
	const error = firstError || (!values.length ? "Add Items to continue" : "")
	return { values: error ? [] : values, problems, error }
}

export function setRowIncluded(row, included) {
	return included ? { ...row, included: true } : {
		...row, included: false, bom: Object.fromEntries(Object.keys(row.bom).map((attribute) => [attribute, null])),
	}
}

export function disableRows(rows, columns) {
	return rows.map((row) => row.included && (!columns.bom.length || columns.bom.some((attribute) => blank(row.bom[attribute]))) ? setRowIncluded(row, false) : row)
}

export function enableRows(rows) {
	return rows.map((row) => row.included ? row : setRowIncluded(row, true))
}

export function fillColumn(rows, column, value) {
	return rows.map((row) => {
		if (!row.included) return row
		return column === "quantity" ? { ...row, quantity: value } : { ...row, bom: { ...row.bom, [column]: value } }
	})
}

export function mappingCardLines(detail) {
	const lines = savedLines(detail?.rows).map((line) => `${Object.values(line.item).join(", ")} -> ${Object.values(line.bom).join(", ")}`)
	return { lines: lines.slice(0, 5), total: lines.length }
}
