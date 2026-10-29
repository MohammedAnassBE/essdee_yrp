import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script"))
const IMPORT = /import \{ vEntryTable \} from "(\.\.\/)+components\/common\/childGrid\/entryTable\.js"/
const DIRECTIVE = /<table[^>]*\sv-entry-table="\{ fixed: false \}"/g

const directiveTables = [
	["sales/ProductionOrderMatrix.vue", 1],
	["sales/ProductionOrderActionDialog.vue", 1],
	["sales/ProductionOrderUpdatePriceDialog.vue", 2],
	["accounts/components/PurchaseInvoiceGroupedItems.vue", 1],
	["cut-panel-store/BoxStickerPrintPage.vue", 1],
]

for (const [path, count] of directiveTables) {
	test(`${path} navigates its editable tables with v-entry-table`, () => {
		const source = read(path)
		assert.match(source, IMPORT)
		assert.equal((templateOf(source).match(DIRECTIVE) || []).length, count)
	})
}

test("production order matrix keeps the read-only lotwise tables out of cell navigation", () => {
	assert.match(templateOf(read("sales/ProductionOrderMatrix.vue")), /<table :style="tableStyle">/)
})

test("cut bundle output table adds a row on Enter and keeps row-select checkboxes out of navigation", () => {
	const source = read("cut-panel-store/CutBundleEditDialog.vue")
	assert.match(source, /\[\[vEntryTable, \{ add: props\.editable \? \(\) => emit\("add"\) : null, fixed: false \}\]\]/)
	assert.match(source, /"data-row-select": "", tabindex: -1/)
})
