export function rowTotal(row) {
	return Object.values(row.values || {}).reduce((total, value) => total + Number(value?.qty || 0), 0)
}

export function deliveredQuantity(blocks) {
	return (blocks || []).reduce((total, block) => total + (block.groups || []).reduce(
		(sum, group) => sum + (group.items || []).reduce((quantity, row) => quantity + rowTotal(row), 0), 0,
	), 0)
}

export function pendingQuantity(cell) {
	return Number(cell?.pending_qty ?? cell?.pending_quantity ?? 0) || 0
}

/** True when every cell of `rows` delivers its full pending quantity and some quantity is pending. */
export function isTableFilled(rows, primaryValues) {
	const cells = (rows || []).flatMap((row) => primaryValues.map((value) => row.values?.[value]).filter(Boolean))
	return cells.some((cell) => pendingQuantity(cell) > 0)
		&& cells.every((cell) => Number(cell.qty || 0) === pendingQuantity(cell))
}

/** Set every cell of `rows` to its pending quantity when `fill`, else to 0, through `setQuantity(row, value, qty)`. */
export function setTableQuantities(rows, primaryValues, fill, setQuantity) {
	for (const row of rows || []) {
		for (const value of primaryValues) {
			const cell = row.values?.[value]
			if (cell) setQuantity(row, value, fill ? pendingQuantity(cell) : 0)
		}
	}
}

function roundQuantity(value) {
	return Math.round(Number(value || 0) * 1000) / 1000
}

function sum(values) {
	return roundQuantity(values.reduce((total, value) => total + Number(value || 0), 0))
}

function hasOneUnit(units) {
	return new Set(units.filter(Boolean)).size <= 1
}

/**
 * Footer totals for one item table. Quantity totals are null when rows use different UOMs;
 * a size's secondary total is null when its cells use different secondary UOMs.
 */
export function getTableTotals(rows, primaryValues, { uom = rowUom, secondaryUom = cellSecondaryUom, pending = pendingQuantity, amount } = {}) {
	const items = rows || []
	const sameUom = hasOneUnit(items.map(uom))
	const cells = (value) => items.map((row) => row.values?.[value]).filter(Boolean)
	const totals = { quantities: {}, pending: {}, secondary: {}, total: null, amount: amount ? sum(items.map(amount)) : null }
	for (const value of primaryValues) {
		totals.quantities[value] = sameUom ? sum(cells(value).map((cell) => cell.qty)) : null
		totals.pending[value] = sameUom ? sum(cells(value).map(pending)) : null
		const secondaryRows = items.filter((row) => row.values?.[value] && secondaryUom(row, value))
		totals.secondary[value] = hasOneUnit(secondaryRows.map((row) => secondaryUom(row, value)))
			? sum(secondaryRows.map((row) => row.values[value].secondary_qty))
			: null
	}
	if (sameUom) totals.total = sum(items.map(rowTotal))
	return totals
}

function rowUom(row) {
	return String(row.default_uom || row.uom || "").trim()
}

function cellSecondaryUom(row, value) {
	return String(row.values?.[value]?.secondary_uom || row.secondary_uom || "").trim()
}

const returnQuantityFields = ["delivered_quantity", "consumed_quantity", "already_returned", "returnable_quantity", "return_quantity"]

/** Return popup totals, one entry per UOM so different units are never added together. */
export function getReturnTotalsByUom(rows) {
	const byUom = new Map()
	for (const row of rows || []) {
		const uom = String(row.uom || "").trim()
		if (!byUom.has(uom)) byUom.set(uom, { uom, rows: [] })
		byUom.get(uom).rows.push(row)
	}
	return [...byUom.values()].map(({ uom, rows: uomRows }) => Object.fromEntries([
		["uom", uom], ...returnQuantityFields.map((field) => [field, sum(uomRows.map((row) => row[field]))]),
	]))
}
