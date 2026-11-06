/** PPO rows of the Purchase Order Add PPO dialog: { production_order, item_name }. */
export function productionOrderRows(rows = []) {
	return (rows || []).filter((row) => row?.production_order).map((row) => ({ production_order: row.production_order, item_name: row.item_name || "" }))
}

/** Append a picked search option (name + item) unless that PPO is already listed. */
export function addProductionOrderRow(rows, option) {
	const name = option?.name
	if (!name || rows.some((row) => row.production_order === name)) return rows
	return [...rows, { production_order: name, item_name: option.item || option.description || "" }]
}

export function removeProductionOrderRow(rows, name) {
	return rows.filter((row) => row.production_order !== name)
}

export function productionOrderNames(rows) {
	return rows.map((row) => row.production_order)
}

export function hasProductionOrderChanges(original, rows) {
	return productionOrderNames(original).join("\n") !== productionOrderNames(rows).join("\n")
}
