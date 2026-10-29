import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../../essdee_yrp/public/js/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script setup>"))
const helper = 'from "yrp/public/js/utils/entryGrid.js"'

function assertSelectionColumn(template) {
	assert.match(template, /<input type="checkbox" data-row-select :checked="[^"]*isAllSelected\.value"/)
	assert.match(template, /<input type="checkbox" data-row-select tabindex="-1"/)
	assert.match(template, /<SelectionFooter :count=/)
}

test("IPD accessory items: checkbox delete, Enter on the add form submits", () => {
	const source = read("Item_Po_detail/AccessoryItems.vue")
	const template = templateOf(source)
	assert.ok(source.includes(helper))
	assert.doesNotMatch(template, /icon\('delete'/)
	assertSelectionColumn(template)
	assert.match(template, /v-enter-submits="add_item"/)
	assert.match(template, /removeSelected\(delete_item, \(\) => !read_only\)/)
	assert.match(source, /cur_frm\.doc\.docstatus > 0 \|\| !cur_frm\.has_perm\("write"\)/)
})

test("IPD bundle groups: checkbox delete removes groups through delete_group_item", () => {
	const source = read("Item_Po_detail/BundleGroup.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /icon\('delete'/)
	assertSelectionColumn(template)
	assert.match(template, /delete_group_item\(grp_items\.find\(\(item\) => item\.id === id\)\)/)
	assert.match(template, /@click="add_groups\(\)"/)
})

test("IPD embellishment: approved panels-only mode hides selection, one Enter-submit form", () => {
	const source = read("Item_Po_detail/EmblishmentDetails.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /icon\('delete'/)
	assertSelectionColumn(template)
	assert.match(source, /can_remove = computed\(\(\) => can_write && !panels_only\.value\)/)
	assert.match(template, /<th v-if="can_remove"/)
	assert.equal(template.match(/v-enter-submits="add_process"/g).length, 1)
	assert.match(template, /@change="toggle_panel\(item, panel, \$event\.target\.checked\)"/)
})

test("fabric swap pairs: per-card selection, Enter adds a pair, locked shows no checkboxes", () => {
	const source = read("Item_Po_detail/FabricSwapDetail.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /remove_pair\(gi, pi\)/)
	assertSelectionColumn(template)
	// A new pair is pre-filled with the last "from", so a row only counts as filled once it has a "to".
	assert.match(template, /v-entry-table="\{ add: read_only \? null : \(\) => add_pair\(groups\.indexOf\(group\)\), isRowBlank: \(index\) => !group\.pairs\[index\]\?\.to, fixed: false \}"/)
	assert.match(source, /read_only = computed\(\(\) => locked\.value \|\| cur_frm\.doc\.docstatus > 0/)
	assert.match(template, /@click="remove_group\(gi\)"/)
})

test("fabric process input recipe: checkbox delete and Enter adds an input row", () => {
	const source = read("Fabric/FabricProcesses.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /removeInputMaterial\(ri\)/)
	assertSelectionColumn(template)
	assert.match(template, /v-entry-table="\{ add: addInputMaterial, isRowBlank: /)
	assert.match(source, /removeSelected\(\s*\(key\) => removeInputMaterial\(/)
})
