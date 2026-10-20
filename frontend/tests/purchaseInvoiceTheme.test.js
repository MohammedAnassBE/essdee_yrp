import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const component = (name) => readFileSync(new URL(`../src/departments/accounts/components/${name}`, import.meta.url), "utf8")

test("F-G08 purchase invoice tables tint over the theme surface, not white", () => {
	for (const name of ["PurchaseInvoiceVerification.vue", "PurchaseInvoiceGroupedItems.vue"]) {
		assert.doesNotMatch(component(name), /color-mix\([^;]*white/, name)
	}
	assert.match(component("PurchaseInvoiceVerification.vue"), /\.verification-table__total \{[^}]*var\(--erp-surface\)/)
})
