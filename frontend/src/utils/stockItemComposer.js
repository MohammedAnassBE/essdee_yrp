export const stockRateLabels = {
	stock_entry: "Rate",
	stock_reconciliation: "Rate",
	stock_update: "Valuation Rate",
	lot_transfer: "Rate",
	"YRP Stock Entry": "Rate",
	"YRP Stock Reconciliation": "Rate",
	"YRP Stock Update": "Valuation Rate",
	"SD YRP Lot Transfer": "Rate",
}

export function applyStockUpdateRates(row, rates) {
	const prepared = clone(row)
	for (const [key, value] of Object.entries(prepared.values || {})) {
		value.rate = Number(rates?.[key] || 0)
	}
	return prepared
}

export async function prepareStockUpdateRow(row, warehouse, loadRates) {
	if (!warehouse) throw new Error("Set Warehouse before adding an item.")
	return applyStockUpdateRates(row, await loadRates(row, warehouse))
}

export async function refreshStockUpdateGroupRates(groups, warehouse, loadRates) {
	return Promise.all((groups || []).map(async (group) => ({
		...group,
		items: await Promise.all((group.items || []).map((row) => prepareStockUpdateRow(row, warehouse, loadRates))),
	})))
}

function clone(value) {
	return JSON.parse(JSON.stringify(value ?? {}))
}

export function mergeStockItemDraft(existingRow, draftRow) {
	const existing = clone(existingRow)
	const draft = clone(draftRow)
	const values = {}
	for (const [key, value] of Object.entries(draft.values || {})) {
		values[key] = { ...(existing.values?.[key] || {}), ...value }
	}
	return { ...existing, ...draft, values }
}

export function matchAttributeValues(values, text) {
	const needle = String(text || "").trim().toLowerCase()
	const rank = (value) => {
		const label = String(value).toLowerCase()
		return label === needle ? 0 : label.startsWith(needle) ? 1 : 2
	}
	return (values || [])
		.filter((value) => !needle || String(value).toLowerCase().includes(needle))
		.sort((left, right) => rank(left) - rank(right))
}
