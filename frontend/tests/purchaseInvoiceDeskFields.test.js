import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import {
	PURCHASE_INVOICE_DISPLAY_FIELDS,
	PURCHASE_INVOICE_EDITOR_GROUPS,
	purchaseInvoiceEditorField,
	purchaseInvoiceSaveValues,
} from "../src/departments/accounts/accountsViews.js"

const read = (path) => readFileSync(new URL(`../src/departments/accounts/${path}`, import.meta.url), "utf8")
const editorFields = PURCHASE_INVOICE_EDITOR_GROUPS.flatMap((group) => group.fields)

test("editor shows the Desk header fields in Desk order", () => {
	assert.deepEqual(PURCHASE_INVOICE_EDITOR_GROUPS[0].fields, [
		"supplier", "against", "due_date", "gstin", "pan_no", "posting_date", "posting_time", "do_not_submit_invoice", "status", "amended_from",
	])
	assert.ok(editorFields.includes("billing_supplier"))
})

test("display fields are read-only and never saved; posting time is saved", () => {
	for (const fieldname of PURCHASE_INVOICE_DISPLAY_FIELDS) {
		assert.equal(purchaseInvoiceEditorField(fieldname, {}).read_only, true, fieldname)
	}
	assert.equal(purchaseInvoiceEditorField("posting_time", {}).fieldtype, "Time")
	assert.equal(purchaseInvoiceEditorField("posting_time", {}).read_only, false)
	assert.equal(purchaseInvoiceEditorField("bill_no", { locked_fields: ["bill_no"] }).read_only, true)
	assert.equal(purchaseInvoiceEditorField("gstin", { schema: { gstin: { read_only: true } } }).read_only, true)

	const form = Object.fromEntries(editorFields.map((fieldname) => [fieldname, `${fieldname}-value`]))
	const values = purchaseInvoiceSaveValues(form, editorFields)
	assert.equal(values.posting_time, "posting_time-value")
	for (const fieldname of PURCHASE_INVOICE_DISPLAY_FIELDS) assert.equal(fieldname in values, false, fieldname)
})

test("editor hides empty display fields", () => {
	assert.match(read("PurchaseInvoiceEditorPage.vue"), /!PURCHASE_INVOICE_DISPLAY_FIELDS\.includes\(fieldname\) \|\| hasValue\(form\[fieldname\]\)/)
})

test("details overview groups every Desk field the backend sends, including empty ones", () => {
	const source = read("components/PurchaseInvoiceOverview.vue")
	for (const fieldname of [
		"supplier", "against", "due_date", "gstin", "pan_no", "posting_date", "posting_time", "do_not_submit_invoice", "status",
		"bill_no", "billing_supplier", "bill_date", "bill_tracking", "eligibility_for_itc", "debit_type", "debit_no", "debit_value",
		"total", "total_tax", "grand_total", "in_words", "amended_from", "erp_inv_name", "final_amount", "cancel_without_cancelling_erp_inv", "remarks",
	]) {
		assert.ok(source.includes(`"${fieldname}"`), fieldname)
	}
	assert.equal(source.match(/include-empty/g)?.length, 2)
	assert.doesNotMatch(source, /filter\(\(field\) => field && documentOverviewHasValue/)
})

test("Items and GRNs share one tab with Items first", () => {
	const source = read("components/PurchaseInvoiceTabs.vue")
	assert.match(source, /<Tab value="items">Items &amp; GRNs<\/Tab>/)
	assert.doesNotMatch(source, /value="grns"/)
	const panel = source.slice(source.indexOf('<TabPanel value="items"'), source.indexOf('<TabPanel v-if="workspace.record?.against'))
	assert.ok(panel.indexOf("<PurchaseInvoiceGroupedItems") < panel.indexOf('class="purchase-invoice-grns erp-card"'))
	assert.match(panel, /@click="emit\('open-grn', grn\.grn\)"/)
})
