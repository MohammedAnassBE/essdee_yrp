const PRECISION = 1000

function round(value) {
	return Math.round(Number(value || 0) * PRECISION) / PRECISION
}

export function quantityDraft(rows) {
	return (rows || []).map((row) => ({ ...row, qty: round(row.qty) }))
}

export function quantityErrors(rows) {
	const errors = {}
	const totals = {}
	for (const row of rows) totals[row.item] = round((totals[row.item] || 0) + round(row.qty))
	for (const row of rows) {
		if (!(round(row.qty) > 0)) errors[row.name] = "Quantity must be greater than zero. Delete the row to skip it."
		else if (totals[row.item] > round(row.available)) errors[row.name] = `Only ${round(row.available)} is available.`
	}
	return errors
}

export function hasQuantityChanges(original, draft) {
	if ((original || []).length !== draft.length) return true
	const saved = Object.fromEntries((original || []).map((row) => [row.name, round(row.qty)]))
	return draft.some((row) => saved[row.name] !== round(row.qty))
}

export function quantityPayload(rows) {
	return rows.map((row) => ({ name: row.name, qty: round(row.qty) }))
}
