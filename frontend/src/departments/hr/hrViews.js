export const BILL_TRACKING_STATUS_OPTIONS = [
	"Open",
	"Assigned",
	"Closed",
	"Reopen",
	"Cancelled",
	"Amended",
	"Pending Approval",
	"Cancel Request Approved",
]

export const BILL_TRACKING_LIST_COLUMNS = [
	"supplier",
	"gstin",
	"bill_no",
	"bill_date",
	"invoice_value",
	"received_date",
	"assigned_to",
	"form_status",
]

const BILL_TRACKING_ACTIONS = [
	{ key: "approve_cancel", label: "Approve Cancel Request", icon: "pi pi-check-circle" },
	{ key: "assign", label: "Assign", icon: "pi pi-send" },
	{ key: "bill_received", label: "Bill Received", icon: "pi pi-inbox" },
	{ key: "submit", label: "Submit", icon: "pi pi-check", shortcut: "submit" },
	{ key: "edit", label: "Edit", icon: "pi pi-pencil" },
	{ key: "request_cancel", label: "Request for Cancel", icon: "pi pi-times-circle" },
	{ key: "create_purchase_invoice", label: "Create YRP Purchase Invoice", icon: "pi pi-plus" },
	{ key: "create_erp_purchase_invoice", label: "Create ERP Purchase Invoice", icon: "pi pi-external-link" },
	{ key: "show_purchase_invoice", label: "Show YRP Purchase Invoice", icon: "pi pi-external-link" },
	{
		key: "show_erp_purchase_invoice",
		label: "Show ERP Purchase Invoice",
		icon: "pi pi-external-link",
	},
	{ key: "cancel", label: "Cancel", icon: "pi pi-ban", menuOnly: true, shortcut: "cancel" },
	{ key: "delete", label: "Delete", icon: "pi pi-trash", menuOnly: true },
]

const BILL_TRACKING_PRIMARY_ACTIONS = ["approve_cancel", "assign", "bill_received", "submit", "edit"]

export function assignedToMeFilters(departments) {
	if (!departments?.length) return null
	return [
		["assigned_to", "in", departments],
		["docstatus", "=", 1],
		["form_status", "!=", "Closed"],
	]
}

export function bulkAssignSummary(result = {}) {
	const assigned = result.assigned || []
	const skipped = result.skipped || []
	const billLabel = assigned.length === 1 ? "bill" : "bills"
	let summary = `Assigned ${assigned.length} ${billLabel}.`
	if (!skipped.length) return summary
	const skippedDetails = skipped.map((row) => `${row.name} (${row.reason})`).join(", ")
	return `${summary} Skipped ${skipped.length}: ${skippedDetails}.`
}

export function billTrackingActionItems(capabilities = {}, handlers = {}) {
	const primary = BILL_TRACKING_PRIMARY_ACTIONS.find((key) => capabilities[key]?.allowed)
	return BILL_TRACKING_ACTIONS.filter(({ key }) => capabilities[key]?.allowed).map((action) => ({
		...action,
		label: capabilities[action.key].label || action.label,
		primary: action.key === primary,
		command: handlers[action.key],
	}))
}

export function deliveryPersonLabel(person = {}) {
	return [person.delivery_person, person.delivery_mob_no].filter(Boolean).join(" · ")
}
