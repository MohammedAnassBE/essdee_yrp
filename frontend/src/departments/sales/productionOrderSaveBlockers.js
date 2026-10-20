export function productionOrderSaveBlockers(form, rows) {
	const requiredFields = { item: "Item", production_term: "Production Term", delivery_date: "Delivery Date", dont_deliver_after: "Don't Deliver After" }
	const missing = Object.entries(requiredFields).filter(([field]) => !form[field]).map(([, label]) => label)
	if (!rows.length) missing.push("Select an Item to load its size matrix")
	else if (!rows.some((row) => Number.isFinite(Number(row.quantity)) && Number(row.quantity) > 0)) missing.push("at least one size quantity above 0")
	return missing
}

export function productionOrderDeliveryWarning(deliveryDate, today = new Date()) {
	const currentDate = [today.getFullYear(), String(today.getMonth() + 1).padStart(2, "0"), String(today.getDate()).padStart(2, "0")].join("-")
	return deliveryDate && deliveryDate < currentDate ? "Delivery Date is in the past. Request Approval will be blocked until it is changed." : ""
}
