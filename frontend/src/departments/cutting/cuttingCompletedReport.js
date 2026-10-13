export function normaliseCompletedGroups(value) {
	if (Array.isArray(value)) return value.filter((group) => group?.items)
	if (value?.items) return [value]
	if (value && typeof value === "object") return Object.values(value).filter((group) => group?.items)
	return []
}

export function completedReportSections(groups, showCompletion = false) {
	return normaliseCompletedGroups(groups).flatMap((group, groupIndex) => {
		const items = (group.items || []).filter((item) => showCompletion || Boolean(item.completed))
		if (!items.length) return []

		const attributes = Array.from(group.attributes || [])
		const primaryValues = Array.from(group.primary_attribute_values || [])
		if (!group.is_set_item) {
			return [{
				key: `group-${groupIndex}`,
				group,
				attributes,
				primaryValues,
				items,
				part: "",
				panels: normalisePanels(group?.[group?.stiching_attr]),
			}]
		}

		const partAttribute = group.set_item_attr || items[0]?.set_attr
		const panelMap = group?.[group?.stiching_attr] || {}
		const parts = Array.from(new Set([
			...Object.keys(panelMap && !Array.isArray(panelMap) ? panelMap : {}),
			...items.map((item) => item.attributes?.[partAttribute]).filter(Boolean),
		]))

		return parts.flatMap((part) => {
			const partItems = items.filter((item) => item.attributes?.[partAttribute] === part)
			if (!partItems.length) return []
			return [{
				key: `group-${groupIndex}-part-${part}`,
				group,
				attributes,
				primaryValues,
				items: partItems,
				part,
				panels: [],
			}]
		})
	})
}

export function completionLabel(item) {
	return item?.completed ? "Completed" : "Not completed"
}

function normalisePanels(value) {
	if (Array.isArray(value)) return value.filter(Boolean)
	if (typeof value === "string") return value.split(",").map((panel) => panel.trim()).filter(Boolean)
	return []
}
