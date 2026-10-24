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

// production_api offers Secondary Qty on these item editors, only for Items with a Secondary UOM.
const SECONDARY_QUANTITY_OPERATIONS = new Set(["stock_entry", "stock_update", "purchase_order"])

export function offersSecondaryQuantity(operation, schema) {
	return SECONDARY_QUANTITY_OPERATIONS.has(operation) && Boolean(schema?.secondary_uom)
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
	if (isSameEntryShape(existing, draft)) {
		for (const [key, value] of Object.entries(existing.values || {})) values[key] ??= value
	}
	return { ...existing, ...draft, values }
}

/** Saved sizes the Item no longer lists cannot be edited in the grid, so an edit must keep them. */
function isSameEntryShape(existing, draft) {
	return Boolean(existing.name && existing.primary_attribute)
		&& existing.name === draft.name
		&& existing.primary_attribute === draft.primary_attribute
		&& JSON.stringify(existing.attributes || {}) === JSON.stringify(draft.attributes || {})
}

/** Grid values for a group: the Item's listed values plus any saved value the row still carries. */
export function getEntryPrimaryValues(listedValues, row) {
	if (!row?.primary_attribute) return [...(listedValues || [])]
	return [...new Set([...(listedValues || []), ...Object.keys(row.values || {})])]
}
