import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script"))
const IMPORT = /import \{ vEntryTable \} from "(\.\.\/)+(components\/)?common\/childGrid\/entryTable\.js"/
const count = (template, pattern) => (template.match(new RegExp(pattern.source, "g")) || []).length

const directiveTables = [
	["departments/fabric-store/DeliveryChallanReturnPanel.vue", /<table v-entry-table class="erp-data-table">/, 1],
	["departments/fabric-store/GrnCalculatePanel.vue", /<table v-entry-table class="erp-data-table">/, 1],
	["departments/fabric-store/WorkOrderActionPanel.vue", /<table v-entry-table class="erp-data-table[^"]*">/, 2],
	["departments/fabric-store/WorkOrderActionPanel.vue", /<table v-entry-table="\{ fixed: false \}" class="erp-data-table work-order-recut-table">/, 1],
	["departments/fabric-store/InspectionEntryPanel.vue", /<table v-entry-table="\{ add: \(\) => addSplit\(source\), canAdd: !acting, isRowBlank: \(index\) => isSplitBlank\(source\.splits\[index\]\), fixed: false \}"/, 1],
	["components/stock/StockItemComposer.vue", /<table v-entry-table="\{ fixed: false \}">/, 2],
]

for (const [path, pattern, expected] of directiveTables) {
	test(`${path} navigates its editable table with v-entry-table (${expected})`, () => {
		const source = read(path)
		assert.match(source, IMPORT)
		assert.equal(count(templateOf(source), pattern), expected)
	})
}

test("work order recut quantities are a table, not a div grid", () => {
	const template = templateOf(read("departments/fabric-store/WorkOrderActionPanel.vue"))
	assert.doesNotMatch(template, /work-order-recut-row/)
	assert.match(template, /<td v-for="value in primaryValues\(group\)" :key="value" class="work-order-recut-table__quantity"><InputNumber v-model="row\.values\[value\]\.qty"/)
})

test("inspection splits keep row-select checkboxes out of cell navigation and Enter-add skips zero-quantity rows", () => {
	const source = read("departments/fabric-store/InspectionEntryPanel.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /inspection-entry-panel__split"/)
	assert.match(template, /<td class="inspection-entry-panel__select"><input type="checkbox" class="inspection-entry-panel__checkbox" data-row-select tabindex="-1"/)
	assert.match(source, /function isSplitBlank\(split\) \{ return !Number\(split\?\.qty \|\| 0\) && !split\?\.comments \}/)
})

test("stock composer quantity grids are tables that still stage the item on Enter from the last input", () => {
	const template = templateOf(read("components/stock/StockItemComposer.vue"))
	assert.match(template, /<div v-if="activePrimaryValues\.length" class="stock-composer__quantity-grid" @keydown\.enter="stageFromLastInput">\s*<table v-entry-table/)
	assert.match(template, /<div v-else class="stock-composer__single-quantity" @keydown\.enter="stageFromLastInput">\s*<table v-entry-table/)
	assert.doesNotMatch(template, /stock-composer__quantity-cell/)
	for (const label of ["`${quantityLabel} ${value}`", "`Rate ${value}`", "`${itemSchema.secondary_uom} ${value}`"]) assert.ok(template.includes(`:aria-label="${label}"`), label)
})
