/** Rows the attribute dialog can edit: variant rows with at least one editable attribute. */
export function getEditableAttributeRows(rows = []) {
	return rows.filter((row) => (row.attributes || []).some((entry) => entry.editable))
}

/** Draft values keyed by row name, then attribute, seeded with the saved values. */
export function createAttributeDraft(rows = []) {
	return Object.fromEntries(rows.map((row) => [
		row.name,
		Object.fromEntries((row.attributes || []).map((entry) => [entry.attribute, entry.value || ""])),
	]))
}

/** Allowed values matching the typed text; exact, then prefix matches come first like the server search. */
export function searchAttributeOptions(options = [], text = "") {
	const needle = String(text || "").trim().toLowerCase()
	const matches = options.filter((value) => String(value).toLowerCase().includes(needle))
	if (needle) {
		const rank = (value) => {
			const lower = String(value).toLowerCase()
			return lower === needle ? 0 : lower.startsWith(needle) ? 1 : 2
		}
		matches.sort((left, right) => rank(left) - rank(right))
	}
	return matches.map((value) => ({ name: value, label: value }))
}

/** Changed editable attributes per row, with the saved item code and quantity the server re-checks. */
export function getAttributeChanges(rows = [], draft = {}) {
	const changes = []
	for (const row of rows) {
		const attributes = {}
		for (const entry of row.attributes || []) {
			const value = draft[row.name]?.[entry.attribute] || ""
			if (entry.editable && value !== (entry.value || "")) attributes[entry.attribute] = value
		}
		if (Object.keys(attributes).length) changes.push({ name: row.name, item_code: row.item_code, qty: row.qty, attributes })
	}
	return changes
}

/** First missing required attribute as "Row #n: Attribute is required.", else "". */
export function getMissingAttributeMessage(rows = [], draft = {}) {
	for (const row of rows) {
		for (const entry of row.attributes || []) {
			if (entry.editable && !String(draft[row.name]?.[entry.attribute] || "").trim()) return `Row #${row.idx}: ${entry.attribute} is required.`
		}
	}
	return ""
}
