export function supplierPendingHint(filters) {
	if (!filters.supplier?.trim()) return "Select a Supplier"
	if (!filters.process?.trim()) return "Select a Process"
	return ""
}

export function differenceTone(received, delivered) {
	const difference = Number(received || 0) - Number(delivered || 0)
	if (difference < 0) return "negative"
	return difference > 0 ? "positive" : "zero"
}
