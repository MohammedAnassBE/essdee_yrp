export function attributeValues(editor, attribute) {
	if (!attribute) return []
	return (editor.context?.attributes || []).find((entry) => entry.attribute === attribute)?.values || []
}

export function attributeNames(draft) {
	return (draft?.item_attributes || []).map((row) => row.attribute).filter(Boolean)
}

export function clothNames(draft) {
	return (draft?.cloth_detail || []).map((row) => row.name1).filter(Boolean)
}
