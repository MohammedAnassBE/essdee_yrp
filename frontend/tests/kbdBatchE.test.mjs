import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script"))
const IMPORT = /import \{ vEntryTable \} from "(\.\.\/)+components\/common\/childGrid\/entryTable\.js"/
const DIRECTIVE = /<table[^>]*\sv-entry-table="\{ [^"]*fixed: false \}"/g

const directiveTables = [
	["finishing/components/FinishingEntryMatrix.vue", 1],
	["finishing/components/FinishingPackingEntry.vue", 3],
	["finishing/components/FinishingDispatchEntry.vue", 4],
	["finishing/components/FinishingReworkEntry.vue", 1],
	["finishing/FinishingReworkGroups.vue", 1],
	["finishing/plan/FinishingOldLotTab.vue", 1],
	["sewing/components/SewingQuantityMatrix.vue", 1],
	["sewing/components/SewingConsumptionTable.vue", 1],
	["sewing/components/ClosedWorkOrderGrnEditor.vue", 1],
	["sewing/plan/SewingFiUpdates.vue", 1],
]

for (const [path, count] of directiveTables) {
	test(`${path} navigates its editable tables with v-entry-table`, () => {
		const source = read(path)
		assert.match(source, IMPORT)
		assert.equal((templateOf(source).match(DIRECTIVE) || []).length, count)
	})
}

test("finishing dispatch keeps the read-only packed/balance table out of cell navigation", () => {
	const template = templateOf(read("finishing/components/FinishingDispatchEntry.vue"))
	assert.match(template, /aria-label="Packed and balance boxes">\s*<table class="finishing-table">/)
})

test("finishing entry matrix puts the include check on the input row when reference rows are shown", () => {
	const template = templateOf(read("finishing/components/FinishingEntryMatrix.vue"))
	assert.match(template, /<td :rowspan="rowSpan" class="finishing-table__index"><span>\{\{ index \+ 1 \}\}<\/span><\/td>/)
	assert.match(template, /<td class="finishing-table__type">\s*<input v-if="checkable && references\.length" v-model="modelValue\[colour\]\.checked" type="checkbox"/)
	assert.equal((template.match(/v-model="modelValue\[colour\]\.checked"/g) || []).length, 2)
})

test("sewing fill-remaining checkbox is skipped by cell navigation", () => {
	const template = templateOf(read("sewing/plan/SewingDataEntry.vue"))
	assert.match(template, /<input type="checkbox" data-row-select tabindex="-1" :checked="Boolean\(filledColours/)
})

test("size ratio packing renders only its own table, so the flat sizes table stays in the v-else branch", () => {
	const template = templateOf(read("finishing/components/FinishingPackingEntry.vue"))
	assert.match(template, /<template v-if="mode === 'Size Ratio Packing'">\s*<table v-entry-table/)
	assert.match(template, /<\/footer>\s*<\/template>\s*<table v-else-if="mode === 'Size Wise Packing'"/)
})
