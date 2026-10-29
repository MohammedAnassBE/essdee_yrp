import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../../../yrp/yrp/public/js/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script"))
const HELPER = /from (["'])\.\.\/utils\/entryGrid\.js\1/

test("D2 files use the relative yrp helper and never import essdee_yrp", () => {
	for (const path of ["ProductionOrder/ProductionOrderTable.vue", "ProcessMatrix/EditProcessMatrix.vue", "InspectionEntry/InspectionEntryEditor.vue"]) {
		const source = read(path)
		assert.match(source, HELPER, path)
		assert.doesNotMatch(source, /essdee_yrp/, path)
	}
})

test("production order attribute rows select, delete through remove_row and add from the combination form on Enter", () => {
	const source = read("ProductionOrder/ProductionOrderTable.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /btn-delete-row|remove_row\(blockIdx, rowIdx\)/)
	assert.match(template, /<th v-if="can_edit_rows\(\)" class="th-select"><input type="checkbox" data-row-select/)
	assert.match(template, /<td v-if="can_edit_rows\(\)" class="td-select"><input type="checkbox" data-row-select tabindex="-1"/)
	assert.match(template, /<SelectionFooter :count="selection_for\(block\)\.selected\.length" @delete="delete_selected_rows\(blockIdx\)" \/>/)
	assert.match(template, /v-enter-submits="\(\) => add_attribute_row\(blockIdx\)"/)
	assert.match(template, /@click="remove_block\(blockIdx\)"/)
	assert.match(source, /removeSelected\(\(rowIdx\) => remove_row\(blockIdx, rowIdx\)/)
	assert.match(source, /edit\.value && \(!window\.cur_frm \|\| Boolean\(cur_frm\.perm\?\.\[0\]\?\.write\)\)/)
})

test("process matrix input and output rows select, delete through deleteRow and add on Enter", () => {
	const source = read("ProcessMatrix/EditProcessMatrix.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /deleteRow\(group/)
	for (const side of ["Input", "Output"]) {
		const key = side === "Input" ? "inputs" : "outputs"
		assert.ok(template.includes(`v-entry-table="{ add: canEditRows ? () => addRow(group, '${side}') : null`), side)
		assert.ok(template.includes(`<SelectionFooter :count="selectionFor(group, '${key}').selected.length" @delete="deleteSelectedRows(group, '${key}')" />`), side)
		assert.ok(template.includes(`data-row-select tabindex="-1" :checked="selectionFor(group, '${key}').isSelected(ri)"`), side)
	}
	assert.match(template, /@click="deleteGroup\(gi\)"/)
	assert.match(source, /removeSelected\(\(ri\) => this\.deleteRow\(group, key, ri\)/)
	assert.match(source, /canEditRows\(\) \{\s*return !this\.readonly/)
})

test("inspection entry splits and modal drafts select and delete, drafts add on Enter and keep one row", () => {
	const source = read("InspectionEntry/InspectionEntryEditor.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /ie-btn-remove|removeDraft\(dIdx\)|deleteBottomRow\(group, row\)/)
	assert.match(template, /<th v-if="canEditRows" class="ie-col-select"><input type="checkbox" data-row-select/)
	assert.match(template, /<SelectionFooter :count="splitSelection\(group\.key\)\.selected\.length" @delete="deleteSelectedSplits\(group\.key\)" \/>/)
	assert.match(template, /v-entry-table="\{ add: addDraft, isRowBlank: \(dIdx\) => draftTotal\(drafts\[dIdx\]\) <= 0, fixed: false \}"/)
	assert.match(template, /draftSelection\.removeSelected\(removeDraft, \(\) => drafts\.length > 1\)/)
	assert.match(template, /:disabled="drafts\.length === 1" @change="draftSelection\.toggle\(dIdx/)
	assert.match(source, /canEditRows = computed\(\(\) => !locked\.value/)
	assert.match(source, /drafts\.value = \[_makeBlankDraft\(\)\];\s*draftSelection\.toggleAll\(false\);/)
})
