import { cellValue } from "../../../components/common/entryGrid.js"

export const PROCESS_COST_LIST_PATH = "/merch/process-costs"
export const PROCESS_COST_STATES = ["Draft", "Approval Pending", "Approved", "Rejected", "Expired"]
export const PROCESS_COST_COLUMNS = ["process_name", "item", "supplier", "from_date", "to_date", "lot"]
export const PROCESS_COST_DETAILS = ["lot", "process_name", "item", "uom", "supplier", "supplier_name", "from_date", "to_date", "is_rework", "tax_slab", "attribute"]
export const PROCESS_COST_SECTIONS = [{
	key: "details", label: "Details", icon: "pi pi-calculator",
	fields: [...PROCESS_COST_DETAILS, "is_expired", "depends_on_attribute", "approved_by"],
}]

export function processCostPath(name) {
	return `${PROCESS_COST_LIST_PATH}/${encodeURIComponent(name)}`
}

export function mergeProcessCostRows(values = [], tiers = [], attribute = "") {
	if (!attribute) return tiers.length ? tiers : [{ attribute_value: null, min_order_qty: 0, price: 0 }]
	const labels = new Map(values.map((value) => [value.name, value.label]))
	const existing = tiers.map((tier) => ({ ...tier, attribute_value_label: labels.get(tier.attribute_value) || tier.attribute_value_label || tier.attribute_value }))
	const present = new Set(tiers.map((tier) => tier.attribute_value))
	return [...existing, ...values.filter((value) => !present.has(value.name)).map((value) => ({
		attribute_value: value.name, attribute_value_label: value.label, min_order_qty: 0, price: 0,
	}))]
}

export function buildProcessCostGrid(tiers = []) {
	const rows = tiers.map((tier, index) => ({ key: `tier-${index}`, label: tier.attribute_value_label || tier.attribute_value || "—" }))
	const model = Object.fromEntries(rows.map((row, index) => [row.key, { min_order_qty: tiers[index].min_order_qty, price: tiers[index].price }]))
	return { rows, model }
}

export function processCostGridValues(tiers, model) {
	return tiers.map((tier, index) => ({ ...tier,
		min_order_qty: cellValue(model, `tier-${index}`, "min_order_qty"),
		price: cellValue(model, `tier-${index}`, "price"),
	}))
}

export function validateProcessCostRows(tiers, attribute, values) {
	const cells = {}
	const seen = new Set()
	const allowed = new Set(values.map((value) => value.name))
	for (const [index, tier] of tiers.entries()) {
		const errors = processCostRowErrors(tier, attribute, allowed)
		const pair = JSON.stringify([tier.attribute_value || null, Number(tier.min_order_qty)])
		if (seen.has(pair)) errors.min_order_qty = "Duplicate Attribute Value and Min Order Qty."
		seen.add(pair)
		if (Object.keys(errors).length) cells[`tier-${index}`] = errors
	}
	return { cells, message: tiers.some((tier) => Number(tier.price) > 0) ? "" : "At least one Process Cost Value must have a price greater than 0." }
}

function processCostRowErrors(tier, attribute, allowed) {
	const errors = {}
	if (attribute && !allowed.has(tier.attribute_value)) errors.price = "Select an Attribute Value configured for this Lot and Process."
	for (const [field, label] of [["min_order_qty", "Min Order Qty"], ["price", "Price"]]) {
		if (!isValidProcessCostNumber(tier[field])) errors[field] = `${label} must be a non-negative number.`
	}
	return errors
}

function isValidProcessCostNumber(value) {
	return value !== null && value !== "" && Number.isFinite(Number(value)) && Number(value) >= 0
}

export function processCostActionMessage(action) {
	if (action.action === "Expired") return "Cancels this rate. Work Orders stop using it from now."
	if (action.action === "Delete") return "Delete this Process Cost? This cannot be undone."
	if (action.action === "Approve") return [action.preview, "Approve and submit this Process Cost?"].filter(Boolean).join("\n")
	return `${action.label || action.action} this Process Cost?`
}

export function processCostActions(workspace, { execute, edit, remove, busy = false }) {
	const actions = (workspace.actions || []).map((action, index) => ({
		key: action.action, label: action.label, primary: index === 0,
		disabled: busy || action.allowed === false, disabledReason: action.reason || "",
		severity: ["Reject", "Expired"].includes(action.action) ? "danger" : undefined,
		command: () => execute(action),
	}))
	if (workspace.can_edit) actions.push({ key: "edit", label: "Edit", icon: "pi pi-pencil", disabled: busy, command: edit })
	if (workspace.can_delete) actions.push({ key: "delete", label: "Delete", icon: "pi pi-trash", severity: "danger", menuOnly: true, disabled: busy, command: remove })
	return actions
}

export function processCostFieldError(reason, fields) {
	const message = reason?.message || String(reason)
	const start = message.indexOf('{')
	const end = message.lastIndexOf('}')
	if (start >= 0 && end > start) {
		try {
			const parsed = JSON.parse(message.slice(start, end + 1))
			if (parsed.field_errors) return parsed
		} catch { /* A normal server message can contain braces. */ }
	}
	const matched = fields.filter((field) => message.toLowerCase().includes(field.label.toLowerCase()))
	return { field_errors: Object.fromEntries(matched.map((field) => [field.fieldname, message])), message }
}
