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
