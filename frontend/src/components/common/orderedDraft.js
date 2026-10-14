export function syncOrderedDraft(currentItems, incomingItems, options = {}) {
	const { visible = true, edited = false, clone = (item) => ({ ...item }) } = options
	if (!visible || edited || !Array.isArray(incomingItems)) return currentItems
	return incomingItems.map(clone)
}

export function moveDraftItem(items, index, direction) {
	if (!Array.isArray(items) || !items.length) return items
	const destination = Math.max(0, Math.min(index + direction, items.length - 1))
	if (index < 0 || index >= items.length || destination === index) return items
	return moveTo(items, index, destination)
}

export function reorderDraftItem(items, fromIndex, dropIndex) {
	if (!Array.isArray(items) || fromIndex < 0 || fromIndex >= items.length) return items
	let destination = Math.max(0, Math.min(dropIndex, items.length))
	if (destination > fromIndex) destination -= 1
	if (destination === fromIndex) return items
	return moveTo(items, fromIndex, destination)
}

function moveTo(items, fromIndex, destination) {
	const ordered = [...items]
	const [moved] = ordered.splice(fromIndex, 1)
	ordered.splice(destination, 0, moved)
	return ordered
}
