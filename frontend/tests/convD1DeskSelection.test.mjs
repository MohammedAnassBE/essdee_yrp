import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../../../yrp/yrp/public/js/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script"))

test("item dimension fetch selects rows, deletes through remove_item and submits the add form on Enter", () => {
	const source = read("Stock/components/ItemDimensionFetch.vue")
	const template = templateOf(source)
	assert.ok(source.includes('from "../../utils/entryGrid.js"'))
	assert.doesNotMatch(source, /essdee_yrp/)
	assert.doesNotMatch(template, /icon\('delete'/)
	assert.equal(template.match(/<th v-if="can_select_rows" class="idf-select"><input type="checkbox" data-row-select/g).length, 2)
	assert.equal(template.match(/<td v-if="can_select_rows" class="idf-select"><input type="checkbox" data-row-select tabindex="-1"/g).length, 2)
	assert.match(template, /<SelectionFooter :count="selection\.selected\.value\.length" @delete="delete_selected" \/>/)
	assert.match(template, /@submit\.prevent="add_item\(\)" v-enter-submits="\(\) => new_item_form\.requestSubmit\(\)"/)
	assert.match(source, /const can_select_rows = computed\(\(\) => Boolean\(props\.edit\) && can_remove\.value\)/)
	assert.match(source, /remove_item\(\.\.\.key\.split\(':'\)\.map\(Number\)\)/)
})

test("GRN editor selects empty splits, keeps one split per row and drops the per-row remove button", () => {
	const source = read("WorkOrder/GoodsReceivedNoteEditor.vue")
	const template = templateOf(source)
	assert.ok(source.includes("from '../utils/entryGrid.js'"))
	assert.doesNotMatch(source, /essdee_yrp/)
	assert.doesNotMatch(template, /grn-rt-remove/)
	assert.match(template, /<th v-if="edit" class="grn-select"><input type="checkbox" data-row-select/)
	assert.match(template, /<td v-if="edit" class="grn-select"><input type="checkbox" data-row-select tabindex="-1"[\s\S]*?:disabled="!canRemoveSplit\(row, split\)"/)
	assert.match(template, /<SelectionFooter :count="selection\.selected\.value\.length" @delete="deleteSelected" \/>/)
	assert.match(source, /if \(split && canRemoveSplit\(row, split\)\) removeSplit\(row, split\)/)
	assert.match(source, /useRowSelection\(\(\) => props\.edit \? logicalRows\.value\.flatMap\(removableKeys\) : \[\]\)/)
})
