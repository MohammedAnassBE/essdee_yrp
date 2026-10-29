import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { ref } from "vue"

import { useRowSelection } from "../src/components/common/childGrid/rowSelection.js"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script setup>"))

test("cut bundle output table selects rows and adds on Enter through its add event", () => {
	const source = read("departments/cut-panel-store/CutBundleEditDialog.vue")
	assert.doesNotMatch(source, /Remove output bundle|cut-bundle-remove/)
	assert.match(source, /useRowSelection\(\(\) => props\.editable \? \(props\.rows \|\| \[\]\)\.map\(\(_, index\) => index\) : \[\]\)/)
	assert.match(source, /selection\.removeSelected\(\(index\) => emit\("remove", index\), \(\) => props\.editable\)/)
	assert.match(source, /"data-row-select": "", tabindex: -1/)
	assert.match(source, /\[\[vEntryTable, \{ add: props\.editable \? \(\) => emit\("add"\) : null, fixed: false \}\]\]/)
	assert.match(source, /label: "Delete", icon: "pi pi-trash", severity: "danger"/)
})

test("finishing packing ratios keep one ratio and move Add Ratio out of the body", () => {
	const source = read("departments/finishing/components/FinishingPackingEntry.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /Remove ratio|pi-times/)
	assert.match(template, /v-entry-table="\{ add: disabled \? null : \(\) => addBatch\(\), fixed: false \}"/)
	assert.match(template, /<\/tbody>\s*<tfoot>\s*<tr class="finishing-table__total-row">/)
	assert.match(template, /<td v-if="!disabled" class="packing-entry__select"><input[^>]*data-row-select tabindex="-1"/)
	assert.match(template, /label="Copy"[^>]*tabindex="-1"/)
	const rowCells = template.slice(template.indexOf('<tr v-for="(batch, index)'), template.indexOf("</tbody>"))
	assert.ok(rowCells.indexOf("Copy") < rowCells.indexOf("<Select"), "Copy sits before the first editable cell")
	assert.match(source, /props\.disabled \|\| state\.batches\.length === 1 \? \[\]/)
	assert.match(source, /removeSelected\(removeBatch, \(\) => !props\.disabled && state\.batches\.length > 1\)/)
})

test("packing ratio delete keeps the last ratio when every ratio is selected", async () => {
	const batches = ref([{ key: 1 }, { key: 2 }, { key: 3 }])
	const selection = useRowSelection(() => batches.value.length === 1 ? [] : batches.value.map((batch) => batch.key))
	selection.toggleAll(true)
	await selection.removeSelected((key) => batches.value.splice(batches.value.findIndex((batch) => batch.key === key), 1), () => batches.value.length > 1)
	assert.deepEqual(batches.value, [{ key: 1 }])
})

test("BOM mapping attribute tables select rows per side and hide checkboxes when read only", () => {
	const source = read("departments/merch/ipd/sections/BomMappingDialog.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /Remove \$\{side\.title\} row/)
	assert.match(template, /<th v-if="!readOnly" scope="col" class="bom-mapping-select"><input type="checkbox"/)
	assert.match(template, /<td v-if="!readOnly" class="bom-mapping-select"><input[^>]*data-row-select tabindex="-1"/)
	assert.match(template, /@click="deleteSelected\(side\.field\)"/)
	assert.match(source, /useRowSelection\(\(\) => readOnly\.value \? \[\] : tables\.value\[field\]\.map\(\(_, index\) => index\)\)/)
	assert.match(source, /tables\.value\[field\]\.splice\(index, 1\), \(\) => !readOnly\.value && !saving\.value\)/)
})

test("item price values select tiers by key and delete through removeTier", () => {
	const source = read("departments/purchase/ItemPriceEditor.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /Remove row|price-values-grid__remove/)
	assert.match(template, /v-entry-table="\{ add: saving \? null : addTier \}"/)
	assert.match(template, /data-row-select tabindex="-1" :checked="tierSelection\.isSelected\(data\.key\)"/)
	assert.ok(template.indexOf("price-values-grid__select") < template.indexOf('header="No."'), "checkbox column comes first")
	assert.match(source, /removeTier\(form\.item_price_values\.findIndex\(\(row\) => row\.key === key\)\)/)
})

test("GRN Dia and lot sub-rows delete through row checkboxes and keep their remove guards", () => {
	const source = read("departments/fabric-store/GoodsReceivedNoteWorkspace.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /aria-label="Remove Dia"|label="Remove"/)
	assert.match(template, /<td v-if="hasSubRowSelect && block.kind === 'items'" class="grn-row-select"><input[^>]*data-row-select tabindex="-1"[^>]*:disabled="!canRemoveSubRow\(section\.group, row\)"/)
	assert.match(template, /@click="deleteSelectedSubRows\(section\)"/)
	assert.match(source, /\(hasActualDia\.value && canRemoveActualDia\(row\)\) \|\| \(canEditLots\.value && canRemoveLot\(group, row\)\)/)
	assert.match(source, /removalOrder\(section\.items, chosen\)\) if \(canRemoveSubRow\(section\.group, row\)\) removeLot\(section\.group, row\)/)
	assert.match(source, /\(hasSubRowSelect\.value \? 1 : 0\)/)
})
