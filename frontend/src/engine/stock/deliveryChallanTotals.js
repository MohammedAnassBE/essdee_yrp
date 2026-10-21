export function rowTotal(row) {
	return Object.values(row.values || {}).reduce((total, value) => total + Number(value?.qty || 0), 0)
}

export function deliveredQuantity(blocks) {
	return (blocks || []).reduce((total, block) => total + (block.groups || []).reduce(
		(sum, group) => sum + (group.items || []).reduce((quantity, row) => quantity + rowTotal(row), 0), 0,
	), 0)
}
