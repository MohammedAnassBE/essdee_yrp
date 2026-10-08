export function formatIsoDate(value) {
	const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/)
	return match ? `${match[3]}-${match[2]}-${match[1]}` : String(value || "")
}

export function addDaysToIsoDate(value, days) {
	const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/)
	if (!match) return ""
	const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])))
	date.setUTCDate(date.getUTCDate() + Number(days || 0))
	return date.toISOString().slice(0, 10)
}

export function validatePurchaseOrderItems(form, groups) {
	for (const group of groups || []) {
		for (const row of group.items || []) {
			const item = row.name || row.item_code || "This item"
			const requiredBy = row.schedule_date || form?.schedule_date || ""
			if (!requiredBy) {
				return `${item} needs a Required By date. Edit this item and select the date.`
			}
			if (form?.transaction_date && requiredBy < form.transaction_date) {
				return `${item} has Required By ${formatIsoDate(requiredBy)}, which is before Order Date ${formatIsoDate(form.transaction_date)}. Edit this item and choose a Required By date on or after the Order Date.`
			}
		}
	}
	return ""
}
