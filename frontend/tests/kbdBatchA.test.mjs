import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script"))
const IMPORT = /import \{ vEntryTable \} from "(\.\.\/)+components\/common\/childGrid\/entryTable\.js"/

const directiveTables = [
	["cutting/shared/CuttingQuantityMatrix.vue", /<table v-entry-table="\{ fixed: false \}">/, 1],
	["cutting/CuttingMarkerDialog.vue", /<table v-entry-table class="marker-table">/, 1],
	["cutting/CuttingLaySheetDialog.vue", /aria-label="Bundle generation groups"><table v-entry-table class="laysheet-table">/, 1],
	["CuttingBulkLaySheet.vue", /aria-label="Bundle generation groups"><table v-entry-table>/, 1],
	["cutting/LotTransferQuantityEditor.vue", /<table v-entry-table class="lt-quantity-table">/, 1],
	["cutting/WorkOrderDeliveryMatrix.vue", /<table v-entry-table="\{ fixed: false \}">/, 1],
	["cutting/CutPanelMovementEditor.vue", /<table v-entry-table class="erp-table">/g, 2],
]

for (const [path, pattern, count] of directiveTables) {
	test(`${path} navigates its editable table with v-entry-table`, () => {
		const source = read(path)
		assert.match(source, IMPORT)
		const matches = templateOf(source).match(new RegExp(pattern.source, "g")) || []
		assert.equal(matches.length, count)
	})
}

test("lot transfer quantities keep the row-select checkbox out of cell navigation", () => {
	const template = templateOf(read("cutting/LotTransferQuantityEditor.vue"))
	assert.match(template, /data-row-select tabindex="-1"/)
})

test("cutting order combination matrices wrap their table in vEntryTable without adding rows", () => {
	const source = read("cutting/order/CuttingOrderDetailDialog.vue")
	const matrix = source.slice(source.indexOf("const CombinationMatrix"))
	assert.match(matrix, /withDirectives\(h\("table", \{ class: "detail-table combination-table" \}/)
	assert.match(matrix, /\]\), \[\[vEntryTable\]\]\)\)/)
})
