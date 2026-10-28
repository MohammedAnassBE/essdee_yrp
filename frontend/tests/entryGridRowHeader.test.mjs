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

test("the column settings gear sits in the trailing header cell, not the row header", () => {
	const source = fs.readFileSync(new URL("../src/components/common/EntryGrid.vue", import.meta.url), "utf8")
	const corner = source.match(/<th scope="col" class="entry-grid__corner"[^\n]*/)[0]
	const trailing = source.match(/<th v-if="hasTrailingColumn"[^\n]*/)[0]
	assert.doesNotMatch(corner, /ChildGridSettings/)
	assert.match(trailing, /<ChildGridSettings/)
})
