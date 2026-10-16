import { renameClothLabels } from "../ipdEditor.js"

export function clothDetailChanges(draft, nextRows) {
	const before = draft.cloth_detail || []
	const renames = new Map()
	nextRows.forEach((row, index) => {
		const old = before[index]
		if (!old || (old.name && old.name !== row.name) || !old.name1 || old.name1 === row.name1 || !row.name1) return
		renames.set(old.name1, row.name1)
	})
	return { cloth_detail: nextRows, ...renameClothLabels(draft, renames) }
}

export function duplicateClothNames(rows) {
	const seen = new Set()
	const duplicates = new Set()
	for (const row of rows || []) {
		if (!row.name1) continue
		if (seen.has(row.name1)) duplicates.add(row.name1)
		seen.add(row.name1)
	}
	return [...duplicates]
}
