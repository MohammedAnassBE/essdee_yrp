export function allowedLotsForEntry(entry, lotOptions) {
	const references = Object.values(entry.values || {}).map((cell) => cell.ref_docname).filter(Boolean)
	if (!references.length && entry.ref_docname) references.push(entry.ref_docname)
	if (!references.length) return []
	const allowed = references.map((reference) => Array.isArray(lotOptions?.[reference]) ? lotOptions[reference] : [])
	return [...new Set(allowed[0])].filter((lot) => lot && allowed.every((lots) => lots.includes(lot)))
}

export function lotChoicesForEntry(entry, lotOptions, lotFieldname, lotItems = {}) {
	const allowed = allowedLotsForEntry(entry, lotOptions)
	const choice = (lot, disabled) => ({ label: lot, value: lot, description: lotItems[lot] || "", disabled })
	const choices = allowed.map((lot) => choice(lot, false))
	const current = entry.dimensions?.[lotFieldname]
	if (current && !allowed.includes(current)) choices.push(choice(current, true))
	return choices
}

export function lotNamesInOptions(lotOptions) {
	return [...new Set(Object.values(lotOptions || {}).flat().filter(Boolean))]
}

export function canEditLotForEntry(entry, lotOptions, lotFieldname) {
	const allowed = allowedLotsForEntry(entry, lotOptions)
	const current = entry.dimensions?.[lotFieldname]
	return allowed.length > 1 || (current ? !allowed.includes(current) : allowed.length > 0)
}

export function itemsNeedLotEditor(items, lotOptions, lotFieldname) {
	return Boolean(lotFieldname) && (items || []).some((group) =>
		(group.items || []).some((entry) => canEditLotForEntry(entry, lotOptions, lotFieldname)))
}

export function unusedLotsForEntry(entry, lotOptions, usedLots) {
	return allowedLotsForEntry(entry, lotOptions).filter((lot) => !usedLots.has(lot))
}
