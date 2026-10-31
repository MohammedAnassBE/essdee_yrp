import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

const read = (file) => fs.readFileSync(new URL(`../src/departments/${file}`, import.meta.url), "utf8")
const importsDirective = /import \{ vEntryTable \} from "\.\.\/\.\.\/\.\.\/components\/common\/childGrid\/entryTable\.js"/

const composers = ["purchase/lot/LotOrderItemsEditor.vue"]
const orderDetails = ["purchase/lot/LotOrderDetailsEditor.vue"]

for (const file of composers) {
	test(`${file}: the box quantity composer grid uses v-entry-table with fixed rows`, () => {
		const source = read(file)
		assert.match(source, importsDirective)
		assert.match(source, /<table v-entry-table class="erp-data-table lot-table">/)
		assert.doesNotMatch(source, /v-entry-table="\{ add/)
		assert.match(source, /@keydown\.enter="addOnLastEnter"/)
	})
}

for (const file of orderDetails) {
	test(`${file}: every order detail group table uses v-entry-table across its per-row tbodies`, () => {
		const source = read(file)
		assert.match(source, importsDirective)
		assert.match(source, /<table v-entry-table class="erp-data-table lot-table">/)
		assert.match(source, /<tbody v-for="\(item, index\) in group\.items"/)
	})
}

test("merch/process-cost/ProcessCostGrid.vue: Enter on the last cell adds a tier through the existing Add tier", () => {
	const source = read("merch/process-cost/ProcessCostGrid.vue")
	assert.match(source, /:add-row="readonly \|\| \(attribute && !tierValue\) \? null : addTier"/)
	assert.match(source, /<Button label="Add tier"[^>]*:disabled="attribute && !tierValue" @click="addTier"/)
})
