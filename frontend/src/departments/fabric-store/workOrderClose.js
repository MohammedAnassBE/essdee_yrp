export function pendingWorkOrderGroups(groups = []) {
	return groups.map(group => ({
		...group,
		items: (group.items || []).filter(item => Number(item.total_delivered || 0) - Number(item.total_received || 0) > 0),
	})).filter(group => group.items.length)
}
