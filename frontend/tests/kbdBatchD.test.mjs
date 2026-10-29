import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script"))
const IMPORT = /import \{ vEntryTable \} from "(\.\.\/)+components\/common\/childGrid\/entryTable\.js"/

test("item dependent attribute table navigates with v-entry-table and never adds rows", () => {
	const source = read("purchase/item/ItemDependentAttributeTable.vue")
	assert.match(source, IMPORT)
	assert.match(templateOf(source), /<table v-entry-table class="erp-data-table dependent-attribute-table">/)
})

for (const path of ["purchase/item/ItemAdditionalParameters.vue", "purchase/item/ItemUomConversions.vue", "purchase/item/ItemYarnRatio.vue"]) {
	test(`${path} grid adds rows on Enter through ChildGridTable`, () => {
		const template = templateOf(read(path))
		assert.match(template, /<ChildGridTable [^>]*:can-add="editable && !disabled[^"]*" :add="addRow"/)
	})
}

test("item price tiers add a row on Enter and keep the row-select checkbox out of navigation", () => {
	const template = templateOf(read("purchase/ItemPriceEditor.vue"))
	assert.match(template, /<DataTable [^>]*v-entry-table="\{ add: saving \? null : addTier \}"/)
	assert.match(template, /data-row-select tabindex="-1"/)
})

for (const [path, count] of [["pd/components/ProductFieldsPanel.vue", 1], ["pd/components/LotwiseCostSections.vue", 5]]) {
	test(`${path} renders its child tables through ChildTableField`, () => {
		assert.equal((templateOf(read(path)).match(/<ChildTableField\b/g) || []).length, count)
	})
}
