export const CLOSE_REASONS = ["", "NA", "Cutting Shortage", "Printing Shortage", "Sewing Shortage", "Sewing Missing", "Others"]

export function bulkCloseFilterHint(filters) {
	if (!filters.supplier?.trim()) return "Select a supplier to load Work Orders."
	if (filters.wo_from_date && filters.wo_to_date && filters.wo_from_date > filters.wo_to_date) return "WO From Date cannot be after WO To Date."
	return ""
}

export function closeReasonHint(values) {
	if (!values.close_reason) return "Select a Close Reason."
	if (values.close_reason === "Others" && !values.close_other_reason.trim()) return "Enter the Other Reason."
	return ""
}

export function sortedWorkOrders(rows, direction) {
	return [...rows].sort((left, right) => (
		String(left.wo_date || "").localeCompare(String(right.wo_date || "")) || String(left.name).localeCompare(String(right.name))
	) * (direction === "asc" ? 1 : -1))
}

export function pendingSummary(groups = []) {
	return groups.map((group) => ({
		...group,
		items: (group.items || []).map((item) => {
			const values = Object.values(item.values || {})
			const total = (key) => values.reduce((sum, value) => sum + Number(value?.[key] || 0), 0)
			return { ...item, total_qty: total("qty"), total_delivered: total("delivered"), total_received: total("received") }
		}).filter((item) => item.total_delivered - item.total_received > 0),
	})).filter((group) => group.items.length)
}
