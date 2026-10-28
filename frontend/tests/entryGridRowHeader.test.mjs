import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

import { rowHeaderColumnWidth } from "../src/components/common/entryGrid.js"

const rows = (count) => Array.from({ length: count }, (_, index) => ({ label: String(index + 1) }))

test("a # index column fits up to three-digit row numbers in 44px", () => {
	assert.equal(rowHeaderColumnWidth(rows(3), true), 44)
	assert.equal(rowHeaderColumnWidth(rows(120), true), 44)
	assert.equal(rowHeaderColumnWidth([], true), 44)
	assert.equal(rowHeaderColumnWidth(rows(1200), true), 52)
})

test("a label row header keeps 140-280px", () => {
	assert.equal(rowHeaderColumnWidth([{ label: "Red" }]), 140)
	assert.equal(rowHeaderColumnWidth([{ label: "A".repeat(20) }]), 188)
	assert.equal(rowHeaderColumnWidth([{ label: "A".repeat(60) }]), 280)
})

test("the column settings gear sits alone in the trailing header cell, with no focusable body cell after the last column", () => {
	const source = fs.readFileSync(new URL("../src/components/common/EntryGrid.vue", import.meta.url), "utf8")
	const corner = source.match(/<th scope="col" class="entry-grid__corner"[^\n]*/)[0]
	const trailing = source.match(/<th v-if="hasTrailingColumn"[^\n]*/)[0]
	assert.doesNotMatch(corner, /ChildGridSettings/)
	assert.match(trailing, /<ChildGridSettings/)
	assert.match(source, /const hasTrailingColumn = gridSettings\.canConfigure\n/)
	assert.match(source, /<td v-if="hasTrailingColumn" \/>\n\t+<\/tr>\n\t+<\/tbody>/)
	assert.doesNotMatch(source, /pi-times|entry-grid__remove/)
})

test("removable grids select rows with left checkboxes and delete them through remove-row", () => {
	const source = fs.readFileSync(new URL("../src/components/common/EntryGrid.vue", import.meta.url), "utf8")
	assert.match(source, /<th v-if="isRemovable" scope="col" class="entry-grid__select" @keydown\.stop><input type="checkbox"[^>]*rowSelection\.toggleAll/)
	assert.match(source, /<td v-if="isRemovable" class="entry-grid__select" @keydown\.stop><input type="checkbox"[^>]*data-row-select tabindex="-1"/)
	assert.match(source, /<footer v-if="rowSelection\.selected\.value\.length" class="entry-grid__footer">[\s\S]*?<Button label="Delete"[^>]*severity="danger"[^>]*@click="deleteSelectedRows"/)
	assert.match(source, /removeSelected\(\(key\) => emit\("remove-row", key\), \(\) => isRemovable\.value\)/)
	assert.match(source, /const isRemovable = computed\(\(\) => props\.removableRows && !props\.readonly\)/)
	assert.match(source, /const reservedWidth = computed\(\(\) => \(isRemovable\.value \? SELECT_WIDTH : 0\) \+ rowHeaderWidth\.value/)
})
