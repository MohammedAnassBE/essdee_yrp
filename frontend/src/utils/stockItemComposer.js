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
