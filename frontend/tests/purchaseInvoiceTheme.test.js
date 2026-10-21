import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const component = (name) => readFileSync(new URL(`../src/departments/accounts/components/${name}`, import.meta.url), "utf8")

test("F-G15 invoice and bill editors share the shell background in both themes", () => {
	for (const [path, selector] of [["accounts/PurchaseInvoiceEditorPage.vue", "purchase-invoice-editor"], ["hr/BillTrackingEditorPage.vue", "bill-tracking-editor"]]) {
		const source = readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")
		const rule = source.match(new RegExp(`\\.${selector} \\{([^}]+)\\}`))[1]
		assert.match(rule, /background: var\(--erp-bg\);/)
		assert.doesNotMatch(rule, /background: color-mix/)
	}
})

test("F-G08 purchase invoice tables tint over the theme surface, not white", () => {
	for (const name of ["PurchaseInvoiceVerification.vue", "PurchaseInvoiceGroupedItems.vue"]) {
		assert.doesNotMatch(component(name), /color-mix\([^;]*white/, name)
	}
	assert.match(component("PurchaseInvoiceVerification.vue"), /\.verification-table__total \{[^}]*var\(--erp-surface\)/)
})
