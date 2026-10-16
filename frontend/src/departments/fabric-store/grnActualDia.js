function cells(row) { return Object.values(row.values || {}) }
function references(row) { return [...new Set(cells(row).map((value) => value.ref_docname).filter(Boolean))].sort() }
function siblingKey(row) { return JSON.stringify(references(row)) }
export function diaSiblings(group, row) {
	if (!references(row).length) return [row]
	return (group.items || []).filter((entry) => siblingKey(entry) === siblingKey(row))
}
export function unusedDias(group, row, context, includeOwn = false) {
	const used = new Set(diaSiblings(group, row).filter((entry) => !includeOwn || entry !== row).map((entry) => entry.attributes?.[context.attribute]))
	const options = context.dia_options || []
	const own = row.attributes?.[context.attribute]
	return [...new Set(includeOwn && own ? [...options, own] : options)].filter((dia) => !used.has(dia))
}
export function changeActualDia(row, attribute, dia) {
	row.attributes ||= {}
	row.attributes[attribute] = dia
	delete row.item_variant
	for (const value of cells(row)) delete value.item_variant
	delete row.actual_dia_error
}
export function addActualDia(group, row, context, dia) {
	if (!unusedDias(group, row, context).includes(dia)) return null
	const entry = JSON.parse(JSON.stringify(row))
	// name is the template used by ungroup_items_from_ui to resolve the variant.
	for (const key of ["row_index", "table_index", "actual_dia_error"]) delete entry[key]
	entry.is_added_actual_dia = true
	for (const value of cells(entry)) {
		for (const key of ["name", "grn_item_name", "original_item_variant", "is_saved_actual_dia", "row_index", "table_index", "amount"]) delete value[key]
		for (const key of ["qty", "secondary_qty", "freight_amount"]) value[key] = 0
	}
	changeActualDia(entry, context.attribute, dia)
	group.items.push(entry)
	return entry
}
export function canRemoveActualDia(row) {
	if (cells(row).length && cells(row).every((value) => value.grn_item_name && value.is_saved_actual_dia)) return true
	return Boolean(row.is_added_actual_dia) && cells(row).every((value) => !Number(value.qty) && !Number(value.secondary_qty))
}
export function receivableBalance(group, row) {
	const siblings = diaSiblings(group, row)
	const pending = new Map()
	for (const entry of siblings) for (const value of cells(entry)) {
		if (value.ref_docname && !pending.has(value.ref_docname)) pending.set(value.ref_docname, Number(value.pending_quantity ?? value.pending_qty ?? 0))
	}
	return [...pending.values()].reduce((sum, value) => sum + value, 0) - siblings.reduce((sum, entry) => sum + cells(entry).reduce((quantity, value) => quantity + Number(value.qty || 0), 0), 0)
}
export function prepareActualDiaGroups(groups, context) {
	if (!context?.enabled) return groups
	return groups.map((group) => {
		if (group.primary_attribute !== context.attribute) return group
		const items = group.items.flatMap((row) => Object.entries(row.values || {}).filter(([, value]) => value.ref_docname).map(([dia, value]) => ({
			...row, attributes: { ...row.attributes, [context.attribute]: dia }, primary_attribute: null, values: { default: value },
		})))
		return { ...group, primary_attribute: null, primary_attribute_values: [], attributes: [...new Set([...(group.attributes || []), context.attribute])], items }
	})
}
export function setActualDiaRowError(groups, message) {
	const match = String(message).match(/Row\s+(\d+):/i)
	if (!match) return false
	const rows = groups.flatMap((group) => group.items || []).flatMap((row) => cells(row).filter((value) => Number(value.qty) > 0).map(() => row))
	const row = rows[Number(match[1]) - 1]
	if (!row) return false
	row.actual_dia_error = message
	return true
}
