import { departmentDeskReports } from "../../components/reports/deskReportConfig.js"

export const ACCOUNTS_REPORTS = [
	{ key: "stock_balance", value: "stock-balance", label: "Stock Balance", icon: "pi pi-warehouse" },
	{ key: "cutting_dpr", value: "cutting-dpr", label: "Cutting DPR", icon: "pi pi-chart-line" },
	{ key: "sewing_dpr", value: "sewing-dpr", label: "Sewing DPR", icon: "pi pi-chart-bar" },
	{
		key: "finishing_dispatch",
		value: "finishing-dispatch",
		label: "Finishing Dispatch",
		icon: "pi pi-truck",
	},
	{ key: "ironing_dpr", value: "ironing-dpr", label: "Ironing DPR", icon: "pi pi-sliders-h" },
	{ key: "audit_pending_finishing_plans", value: "audit-pending", label: "Audit Pending", icon: "pi pi-check-square" },
]

export const PURCHASE_INVOICE_STATUS_OPTIONS = [
	"Draft",
	"Approval Initiated",
	"Approval Pending",
	"Approved",
	"Submitted",
	"Cancelled",
]

export const PURCHASE_INVOICE_LIST_COLUMNS = [
	"supplier",
	"bill_no",
	"posting_date",
	"against",
	"grand_total",
	"status",
]

export const PURCHASE_INVOICE_EDITOR_GROUPS = [
	{ key: "invoice", eyebrow: "Document", label: "Invoice", fields: ["supplier", "against", "posting_date", "due_date", "do_not_submit_invoice"] },
	{ key: "supplier-bill", eyebrow: "Vendor invoice", label: "Supplier bill", fields: ["bill_no", "billing_supplier", "bill_date", "eligibility_for_itc"] },
	{ key: "debit", eyebrow: "Adjustment", label: "Debit", fields: ["debit_type", "debit_no", "debit_value"] },
	{ key: "notes", eyebrow: "Context", label: "Notes", fields: ["remarks"] },
]

const PURCHASE_INVOICE_FALLBACK_SCHEMA = {
	supplier: { label: "Supplier", fieldtype: "Link", options: "Supplier", reqd: true },
	against: { label: "Against", fieldtype: "Select", options: "Purchase Order\nYRP Work Order", reqd: true },
	posting_date: { label: "Posting Date", fieldtype: "Date", reqd: true },
	due_date: { label: "Due Date", fieldtype: "Date" },
	do_not_submit_invoice: { label: "Do not submit Invoice", fieldtype: "Check" },
	bill_no: { label: "Supplier Invoice No", fieldtype: "Data", reqd: true },
	billing_supplier: { label: "Billing Supplier", fieldtype: "Link", options: "Supplier", reqd: true },
	bill_date: { label: "Supplier Invoice Date", fieldtype: "Date", reqd: true },
	eligibility_for_itc: { label: "Eligibility For ITC", fieldtype: "Select" },
	debit_type: { label: "Debit Type", fieldtype: "Select" },
	debit_no: { label: "Debit No", fieldtype: "Data" },
	debit_value: { label: "Debit Value", fieldtype: "Currency" },
	remarks: { label: "Remarks", fieldtype: "Small Text" },
}

const PURCHASE_INVOICE_ACTIONS = [
	{ key: "submit", label: "Submit", icon: "pi pi-check" },
	{ key: "approve", label: "Approve Invoice", icon: "pi pi-check-circle" },
	{ key: "edit", label: "Edit", icon: "pi pi-pencil" },
	{ key: "fetch_expense_head", label: "Fetch Expense Head", icon: "pi pi-book" },
	{ key: "show_erp_bill", label: "Show ERP Bill", icon: "pi pi-external-link" },
	{ key: "submit_erp_bill", label: "Submit ERP Bill", icon: "pi pi-send" },
	{ key: "cancel", label: "Cancel", icon: "pi pi-ban", menuOnly: true },
	{ key: "amend", label: "Amend", icon: "pi pi-copy", menuOnly: true },
	{ key: "delete", label: "Delete", icon: "pi pi-trash", menuOnly: true },
]

const PURCHASE_INVOICE_PRIMARY_ACTIONS = ["submit", "approve", "edit"]

export function accountsReportTabs(reports) {
	return [...ACCOUNTS_REPORTS.filter((report) => reports?.[report.key]?.can_read), ...departmentDeskReports("accounts", reports)]
}

/** Mirror YRPPurchaseInvoice.calculate_total: sum unrounded rows, round the totals once. */
export function groupedItemTotals(rows = [], taxRates = {}) {
	const totals = rows.reduce(
		(result, row) => {
			const quantity = Number(row.qty ?? 0) || 0
			const amount = quantity * (Number(row.rate ?? 0) || 0)
			const taxRate = Number(row.tax_rate ?? taxRates[row.tax] ?? 0) || 0
			result.total += amount
			result.totalTax += amount * taxRate / 100
			result.quantity += quantity
			return result
		},
		{ total: 0, totalTax: 0, quantity: 0 },
	)
	return {
		total: rounded(totals.total),
		totalTax: rounded(totals.totalTax),
		grandTotal: rounded(totals.total + totals.totalTax),
		quantity: rounded(totals.quantity),
	}
}

export function applySupplierChange(state, supplier) {
	return {
		...state,
		values: { ...state.values, supplier, billing_supplier: supplier },
		grns: [],
		items: [],
	}
}

export function mergeKnownGrns(knownRows = [], rows = [], selectedNames = []) {
	const result = []
	const indexes = new Map()
	for (const row of [...(knownRows || []), ...(rows || [])]) {
		const name = String(row?.name || "").trim()
		if (!name) continue
		if (indexes.has(name)) {
			const index = indexes.get(name)
			result[index] = { ...result[index], ...row, name }
			continue
		}
		indexes.set(name, result.length)
		result.push({ ...row, name })
	}
	for (const value of selectedNames || []) {
		const name = String(value || "").trim()
		if (!name || indexes.has(name)) continue
		indexes.set(name, result.length)
		result.push({ name, selected: true })
	}
	return result
}

export function filterEligibleGrns(rows = [], searchText = "", selectedNames = []) {
	const query = String(searchText || "").trim().toLocaleLowerCase()
	if (!query) return rows
	const selected = new Set((selectedNames || []).map((name) => String(name || "").trim()).filter(Boolean))
	return rows.filter((row) => selected.has(row.name) || [row.name, row.against_id, row.supplier_document_no]
		.some((value) => String(value || "").toLocaleLowerCase().includes(query)))
}

export function addGrnsWithinLimit(selectedNames = [], addedNames = [], limit = 200) {
	const result = []
	const names = new Set()
	for (const value of [...(selectedNames || []), ...(addedNames || [])]) {
		const name = String(value || "").trim()
		if (!name || names.has(name)) continue
		names.add(name)
		result.push(name)
		if (result.length >= limit) break
	}
	return result
}

export function purchaseInvoiceEditorField(fieldname, editor = {}) {
	const field = { ...PURCHASE_INVOICE_FALLBACK_SCHEMA[fieldname], ...(editor.schema?.[fieldname] || {}), fieldname }
	if (fieldname === "supplier") field.link_filters = { disabled: 0 }
	if (fieldname === "against") field.options = "Purchase Order\nYRP Work Order"
	field.read_only = (editor.locked_fields || []).includes(fieldname)
	return field
}

export function purchaseInvoicePreviewTotals(rows, taxRates) {
	const totals = groupedItemTotals(rows, taxRates)
	return [
		{ key: "total", label: "Total", value: previewMoney(totals.total) },
		{ key: "tax", label: "Tax", value: previewMoney(totals.totalTax) },
		{ key: "grand-total", label: "Grand Total", value: previewMoney(totals.grandTotal) },
		{ key: "quantity", label: "Quantity", value: previewNumber(totals.quantity) },
	]
}

export function purchaseInvoiceSaveValues(form, fieldnames) {
	const values = Object.fromEntries([...fieldnames, "bill_tracking"].map((fieldname) => [fieldname, form[fieldname]]))
	if (isMaskedValue(values.supplier)) delete values.supplier
	if (isMaskedValue(values.billing_supplier)) delete values.billing_supplier
	return values
}

export function hasValue(value) {
	return value !== null && value !== undefined && String(value).trim() !== ""
}

export function queryValue(value) {
	return Array.isArray(value) ? String(value[0] || "") : String(value || "")
}

export function cloneValue(value) {
	return JSON.parse(JSON.stringify(value ?? null))
}

export function purchaseInvoiceActionItems(capabilities = {}, handlers = {}) {
	const primary = PURCHASE_INVOICE_PRIMARY_ACTIONS.find((key) => capabilities[key]?.allowed)
	return PURCHASE_INVOICE_ACTIONS.filter(({ key }) => capabilities[key]?.allowed).map((action) => ({
		...action,
		label: capabilities[action.key].label || action.label,
		primary: action.key === primary,
		command: handlers[action.key],
	}))
}

export function isCurrentRecordAction(action, current) {
	return action.sequence === current.sequence
		&& action.name === current.name
		&& action.route === current.route
}

export function isMaskedValue(value) {
	return typeof value === "string" && /^[Xx*]+$/.test(value.trim())
}

/** Port of frappe.utils.flt banker's rounding (the site's rounding method) to 2 decimals. */
function rounded(value) {
	const scaled = Number((value * 100).toFixed(12))
	const floor = Math.floor(scaled)
	const epsilon = scaled === 0 ? 0 : 2 ** (Math.log2(Math.abs(scaled)) - 52)
	const isTie = Math.abs(scaled - floor - 0.5) < epsilon
	const result = (isTie ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(scaled)) / 100
	return result === 0 ? 0 : result
}

function previewNumber(value) {
	const numericValue = Number(value)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { maximumFractionDigits: 3 })
		: "0"
}

function previewMoney(value) {
	const numericValue = Number(value)
	return Number.isFinite(numericValue)
		? numericValue.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
		: "0.00"
}
