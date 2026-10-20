export const PURCHASE_ORDER_STATUSES = [
	"Draft",
	"Ordered",
	"Partially Received",
	"Received",
	"Partially Cancelled",
	"Cancelled",
	"Closed",
]

const statusTones = {
	Draft: "warning",
	Ordered: "info",
	"Partially Received": "warning",
	Received: "success",
	"Partially Cancelled": "neutral",
	Cancelled: "neutral",
	Closed: "info",
}

export function purchaseOrderStatusLabel(record) {
	if (Number(record.is_yrp_managed) === 1) return record.yrp_fulfillment_status || record.status || "Draft"
	if (String(record.docstatus) === "0") return "Draft"
	if (String(record.docstatus) === "2") return "Cancelled"
	return record.status || "Draft"
}

export function purchaseOrderStatusTone(label) {
	return statusTones[label] || "info"
}

export const purchaseOrderStatusOptions = PURCHASE_ORDER_STATUSES.map((value) => ({
	label: value,
	value,
	tone: purchaseOrderStatusTone(value),
	filters: [["is_yrp_managed", "=", 1], ["yrp_fulfillment_status", "=", value]],
}))
