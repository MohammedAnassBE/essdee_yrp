#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	ACCOUNTS_REPORTS,
	PURCHASE_INVOICE_EDITOR_GROUPS,
	PURCHASE_INVOICE_LIST_COLUMNS,
	PURCHASE_INVOICE_STATUS_OPTIONS,
	accountsReportTabs,
	addGrnsWithinLimit,
	applySupplierChange,
	filterEligibleGrns,
	groupedItemTotals,
	isCurrentRecordAction,
	isMaskedValue,
	mergeKnownGrns,
	purchaseInvoiceActionItems,
	purchaseInvoiceEditorField,
	purchaseInvoicePreviewTotals,
	purchaseInvoiceSaveValues,
} from "../frontend/src/departments/accounts/accountsViews.js"

assert.deepEqual(
	ACCOUNTS_REPORTS.map((report) => report.key),
	["stock_balance", "cutting_dpr", "sewing_dpr", "finishing_dispatch", "ironing_dpr"],
)
assert.deepEqual(
	accountsReportTabs({ sewing_dpr: { can_read: true } }).map((tab) => tab.value),
	["sewing-dpr"],
)
assert.deepEqual(accountsReportTabs({}), [])

assert.deepEqual(
	groupedItemTotals(
		[
			{ qty: 10, rate: 12.5, tax: "GST 5" },
			{ qty: 2, rate: 100, tax_rate: 12 },
		],
		{ "GST 5": 5 },
	),
	{ total: 325, totalTax: 30.25, grandTotal: 355.25, quantity: 12 },
)
assert.deepEqual(groupedItemTotals([], {}), {
	total: 0,
	totalTax: 0,
	grandTotal: 0,
	quantity: 0,
})
assert.deepEqual(groupedItemTotals([{ qty: 1, rate: 53.5, tax_rate: 5 }]), {
	total: 53.5,
	totalTax: 2.68,
	grandTotal: 56.18,
	quantity: 1,
})
assert.deepEqual(groupedItemTotals([{ qty: 1, rate: 16.9, tax_rate: 5 }]), {
	total: 16.9,
	totalTax: 0.84,
	grandTotal: 17.74,
	quantity: 1,
})
assert.deepEqual(
	groupedItemTotals(Array.from({ length: 33 }, () => ({ qty: 1, rate: 53.5, tax_rate: 5 }))),
	{ total: 1765.5, totalTax: 88.27, grandTotal: 1853.78, quantity: 33 },
)
assert.deepEqual(
	groupedItemTotals(Array.from({ length: 2 }, () => ({ qty: 1, rate: 53.5, tax_rate: 5 }))),
	{ total: 107, totalTax: 5.35, grandTotal: 112.35, quantity: 2 },
)
const tinyTotals = groupedItemTotals([{ qty: 0.001, rate: 0.01, tax_rate: 5 }])
assert.deepEqual(tinyTotals, { total: 0, totalTax: 0, grandTotal: 0, quantity: 0 })
assert.equal(Number.isNaN(tinyTotals.totalTax), false)
assert.deepEqual(groupedItemTotals([{ qty: -1, rate: 16.9, tax_rate: 5 }]), {
	total: -16.9,
	totalTax: -0.84,
	grandTotal: -17.74,
	quantity: -1,
})
const negativeTinyTotals = groupedItemTotals([{ qty: -0.001, rate: 0.01, tax_rate: 5 }])
assert.deepEqual(negativeTinyTotals, { total: 0, totalTax: 0, grandTotal: 0, quantity: 0 })
assert.equal(Object.values(negativeTinyTotals).some((value) => Object.is(value, -0)), false)

assert.equal(PURCHASE_INVOICE_EDITOR_GROUPS.at(-1).key, "notes")
assert.deepEqual(
	purchaseInvoiceEditorField("supplier", { locked_fields: ["supplier"] }),
	{
		label: "Supplier", fieldtype: "Link", options: "Supplier", reqd: true,
		fieldname: "supplier", link_filters: { disabled: 0 }, read_only: true,
	},
)
assert.deepEqual(purchaseInvoicePreviewTotals([{ qty: 2, rate: 10, tax_rate: 5 }], {}), [
	{ key: "total", label: "Total", value: "20.00" },
	{ key: "tax", label: "Tax", value: "1.00" },
	{ key: "grand-total", label: "Grand Total", value: "21.00" },
	{ key: "quantity", label: "Quantity", value: "2" },
])
assert.deepEqual(
	purchaseInvoiceSaveValues({ supplier: "XXXX", bill_no: "B-1", bill_tracking: "BT-1" }, ["supplier", "bill_no"]),
	{ bill_no: "B-1", bill_tracking: "BT-1" },
)

const current = {
	values: { supplier: "A", billing_supplier: "A", bill_no: "INV-1" },
	grns: ["GRN-1"],
	items: [{}],
}
const next = applySupplierChange(current, "B")
assert.deepEqual(
	[next.values.supplier, next.values.billing_supplier, next.grns.length, next.items.length],
	["B", "B", 0, 0],
)
assert.equal(next.values.bill_no, "INV-1")
assert.notEqual(next, current)
assert.notEqual(next.values, current.values)
assert.deepEqual(current.grns, ["GRN-1"])

const eligibleGrns = [
	{ name: "GRN-1", against_id: "PO-100", supplier_document_no: "BILL-A" },
	{ name: "GRN-2", against_id: "WO-200", supplier_document_no: null },
]
assert.deepEqual(filterEligibleGrns(eligibleGrns, "grn-2"), [eligibleGrns[1]])
assert.deepEqual(filterEligibleGrns(eligibleGrns, "po-100"), [eligibleGrns[0]])
assert.deepEqual(filterEligibleGrns(eligibleGrns, "bill-a"), [eligibleGrns[0]])
assert.equal(filterEligibleGrns(eligibleGrns, "missing").length, 0)
assert.strictEqual(filterEligibleGrns(eligibleGrns, ""), eligibleGrns)
assert.deepEqual(filterEligibleGrns(eligibleGrns, "missing", ["GRN-2"]), [eligibleGrns[1]])
const knownGrns = mergeKnownGrns([], eligibleGrns, ["GRN-2", "GRN-SAVED"])
assert.deepEqual(knownGrns, [
	eligibleGrns[0],
	eligibleGrns[1],
	{ name: "GRN-SAVED", selected: true },
])
assert.deepEqual(mergeKnownGrns(knownGrns, [
	{ name: "GRN-SAVED", posting_date: "2026-10-13", selected: false },
	{ name: "GRN-3", against_id: "PO-300" },
], []), [
	eligibleGrns[0],
	eligibleGrns[1],
	{ name: "GRN-SAVED", posting_date: "2026-10-13", selected: false },
	{ name: "GRN-3", against_id: "PO-300" },
])
assert.deepEqual(mergeKnownGrns([], [], ["GRN-SAVED"]), [{ name: "GRN-SAVED", selected: true }])
const selected199 = Array.from({ length: 199 }, (_, index) => `GRN-${index + 1}`)
assert.deepEqual(
	addGrnsWithinLimit(selected199, ["GRN-1", "GRN-200", "GRN-201"], 200),
	[...selected199, "GRN-200"],
)
assert.deepEqual(addGrnsWithinLimit([" GRN-1 ", "GRN-1"], ["", "GRN-2"], 200), ["GRN-1", "GRN-2"])

assert.equal(isMaskedValue("XXXXXX"), true)
assert.equal(isMaskedValue("xxxxxx"), true)
assert.equal(isMaskedValue("******"), true)
assert.equal(isMaskedValue(" Xx** "), true)
assert.equal(isMaskedValue("SUP-1"), false)
assert.equal(isMaskedValue(""), false)
assert.equal(isMaskedValue("   "), false)

const submittedActions = purchaseInvoiceActionItems(
	{
		submit: { allowed: true, label: "Submit" },
		approve: { allowed: true, label: "Approve Invoice" },
		delete: { allowed: true, label: "Delete" },
	},
	{},
)
assert.equal(submittedActions.find((item) => item.primary).key, "submit")
assert.equal(submittedActions.find((item) => item.key === "delete").menuOnly, true)

const approvalActions = purchaseInvoiceActionItems(
	{
		approve: { allowed: true, label: "Approve Invoice" },
		edit: { allowed: true, label: "Edit" },
	},
	{ approve: () => "approved" },
)
assert.equal(approvalActions.find((item) => item.primary).key, "approve")
assert.equal(approvalActions.find((item) => item.key === "approve").command(), "approved")
const editActions = purchaseInvoiceActionItems({ edit: { allowed: true } }, {})
assert.equal(editActions.find((item) => item.primary).key, "edit")

const invoiceAction = { name: "PI-A", route: "/accounts/purchase-invoices/PI-A", sequence: 4 }
assert.equal(isCurrentRecordAction(invoiceAction, { ...invoiceAction }), true)
assert.equal(isCurrentRecordAction(invoiceAction, { ...invoiceAction, name: "PI-B" }), false)
assert.equal(isCurrentRecordAction(invoiceAction, { ...invoiceAction, route: "/accounts/purchase-invoices/PI-B" }), false)
assert.equal(isCurrentRecordAction(invoiceAction, { ...invoiceAction, sequence: 6 }), false)

assert.deepEqual(PURCHASE_INVOICE_STATUS_OPTIONS, [
	"Draft",
	"Approval Initiated",
	"Approval Pending",
	"Approved",
	"Submitted",
	"Cancelled",
])
assert.deepEqual(PURCHASE_INVOICE_LIST_COLUMNS, [
	"supplier",
	"bill_no",
	"posting_date",
	"against",
	"grand_total",
	"status",
])

const accountsRequests = []
globalThis.window = { csrf_token: "" }
globalThis.fetch = async (url, options) => {
	accountsRequests.push({ url, body: JSON.parse(options.body) })
	return { ok: true, status: 200, json: async () => ({ message: {} }) }
}
const { executePurchaseInvoiceCommand, getEligibleGrns, savePurchaseInvoice } = await import("../frontend/src/api/accounts.js")
await savePurchaseInvoice({ values: {}, grns: [], items: [] }, {
	name: "PI-1",
	expectedModified: "2026-10-13 10:00:00.000000",
})
await executePurchaseInvoiceCommand("PI-1", "submit", {}, "2026-10-13 10:00:00.000000")
await savePurchaseInvoice({ values: {}, grns: [], items: [] })
await getEligibleGrns({ supplier: "SUP-1", against: "Purchase Order", searchText: "needle", limit: 200 })
assert.equal(accountsRequests[0].body.expected_modified, "2026-10-13 10:00:00.000000")
assert.equal(accountsRequests[1].body.expected_modified, "2026-10-13 10:00:00.000000")
assert.equal(accountsRequests[2].body.expected_modified, null)
assert.equal(accountsRequests[3].body.limit, 200)
assert.equal(accountsRequests[3].body.search_text, "needle")

console.log("accounts views OK")
