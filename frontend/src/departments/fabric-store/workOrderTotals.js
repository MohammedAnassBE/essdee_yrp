const PRECISION = 1000

function rounded(value) {
	return Math.round(Number(value || 0) * PRECISION) / PRECISION
}

/** Sum each item's stage rows into one total stage per key; rate stages in `skipKeys` are left out. */
export function sumStageRows(stageLists, primaryValues, skipKeys = ["cost"]) {
	const totals = new Map()
	for (const stages of stageLists || []) {
		for (const stage of stages || []) {
			if (skipKeys.includes(stage.key)) continue
			if (!totals.has(stage.key)) totals.set(stage.key, { key: stage.key, label: stage.label, values: Object.fromEntries(primaryValues.map((value) => [value, 0])), total: 0 })
			const total = totals.get(stage.key)
			for (const value of primaryValues) total.values[value] = rounded(total.values[value] + Number(stage.values?.[value] || 0))
			total.total = rounded(total.total + Number(stage.total || 0))
		}
	}
	return [...totals.values()]
}

/** Available and Rework quantity totals for the Create Rework rows. */
export function reworkTotals(rows) {
	return (rows || []).reduce((totals, row) => ({
		available: rounded(totals.available + Number(row.available_qty || 0)),
		qty: rounded(totals.qty + Number(row.qty || 0)),
	}), { available: 0, qty: 0 })
}

/** Per-size and overall recut quantity for one recut group. */
export function recutGroupTotals(group, primaryValues) {
	const values = Object.fromEntries(primaryValues.map((value) => [value, rounded((group.items || []).reduce((total, row) => total + Number(row.values?.[value]?.qty || 0), 0))]))
	return { values, total: rounded(Object.values(values).reduce((total, value) => total + value, 0)) }
}

/** Total recut pieces across every group. */
export function recutPieces(groups) {
	return rounded((groups || []).reduce((total, group) => total + (group.items || []).reduce((rowTotal, row) => rowTotal + Object.values(row.values || {}).reduce((cellTotal, value) => cellTotal + Number(value?.qty || 0), 0), 0), 0))
}

/** Cloth quantity (Kg) to receive across a fabric row's routes. */
export function fabricClothTotal(row) {
	return rounded((row?.entries || []).reduce((total, entry) => total + Number(entry.qty || 0), 0))
}
