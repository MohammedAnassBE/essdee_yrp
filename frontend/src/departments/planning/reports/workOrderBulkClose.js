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

const plural = (count, one, many) => count === 1 ? `1 ${one}` : `${count} ${many}`

/** Counts and messages for the Bulk Close result dialog, mirroring production_api. */
export function bulkCloseOutcome(results = [], failed = []) {
	const closed = results.filter((result) => result.open_status === "Close").length
	const requested = results.filter((result) => result.open_status === "Close Request").length
	return {
		closed, requested, failed,
		summary: `${plural(closed, "Work Order closed", "Work Orders closed")}; ${plural(requested, "close request submitted", "close requests submitted")}.`,
		failedLabel: `${plural(failed.length, "Work Order failed:", "Work Orders failed:")}`,
	}
}
