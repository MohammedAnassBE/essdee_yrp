export function groupAttributes(group) {
	if (Array.isArray(group.attributes) && group.attributes.length) return group.attributes
	const attributes = [group.pack_attr, group.is_set_item && group.set_attr].filter(Boolean)
	return attributes.length ? attributes : Object.keys(group.items?.[0]?.attributes || {})
}

export function itemSections(group) {
	const sections = new Map()
	for (const row of group.items || []) {
		if (!sections.has(row.name)) sections.set(row.name, { name: row.name, rows: [] })
		sections.get(row.name).rows.push(row)
	}
	return [...sections.values()]
}
