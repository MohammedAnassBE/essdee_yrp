import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../../essdee_yrp/public/js/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script"))
const HELPER = 'from "yrp/public/js/utils/entryGrid.js"'

test("action detail selects actions, deletes through delete_item and submits the add form on Enter", () => {
	const source = read("ActionMaster/ActionDetail.vue")
	const template = templateOf(source)
	assert.ok(source.includes(HELPER))
	assert.doesNotMatch(template, /icon\('delete'/)
	assert.match(template, /<th v-if="can_edit" class="row-select">\s*<input type="checkbox" data-row-select/)
	assert.match(template, /<td v-if="can_edit" class="row-select">\s*<input type="checkbox" data-row-select tabindex="-1"/)
	assert.match(template, /<SelectionFooter :count="selected\.length" @delete="removeSelected\(delete_item\)" \/>/)
	assert.match(template, /v-if="show_div" v-enter-submits="add_items"/)
	assert.match(source, /can_edit = computed\(\(\) => !preview\.value && cur_frm\.doc\.docstatus === 0/)
})

test("cut bundle edit output cards select bundles and delete through delete_bundle", () => {
	const source = read("Cut_Bundle_Edit/components/CutBundleEdit.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /delete_bundle\(index\)|cancel-style/)
	assert.match(template, /<input v-if="can_edit" type="checkbox" data-row-select tabindex="-1"/)
	assert.match(template, /<SelectionFooter :count="selected\.length" @delete="removeSelected\(delete_bundle\)" \/>/)
	assert.match(source, /const can_edit = docstatus === 0 && Boolean\(cur_frm\.perm\?\.\[0\]\?\.write\)/)
})

test("cut bundle panel groups select split groups and remove them through removeGroup", () => {
	const source = read("Cut_Bundle_Edit/components/CutBundlePanelGroup.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /x-icon|removeGroup\(panel, index\)/)
	assert.match(template, /data-row-select tabindex="-1" :checked="isSelected\(group_key\(panel, index\)\)"/)
	assert.match(template, /v-enter-submits="add_groups"/)
	assert.match(source, /removeGroup\(\.\.\.JSON\.parse\(key\)\)/)
})

test("finishing GRN ratio batches add on Enter, keep one batch and keep Add Ratio out of the body", () => {
	const source = read("Finishing/FPPopUpGRN.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /remove_batch\(bi\)/)
	assert.match(template, /v-entry-table="\{ add: \(\) => add_batch\(\), fixed: false \}"/)
	assert.match(template, /<\/tbody>\s*<tfoot class="dark-border">/)
	assert.match(template, /tabindex="-1" @click="copy_batch\(batch\)"/)
	assert.match(source, /removeSelected\(key => remove_batch\(ratio_batches\.findIndex\(batch => batch\.key === key\)\), \(\) => ratio_batches\.length > 1\)/)
})

test("lot order items get a checkbox column wired to delete_item and Enter submits the item form", () => {
	const source = read("Lot/components/LotOrder.vue")
	const template = templateOf(source)
	assert.equal(template.match(/<th v-if="can_edit" class="row-select">/g).length, 2)
	assert.equal(template.match(/data-row-select tabindex="-1" :checked="isSelected\(item1_index\)"/g).length, 2)
	assert.match(template, /<SelectionFooter :count="selected\.length" @delete="removeSelected\(delete_item\)" \/>/)
	assert.match(template, /v-enter-submits="\(\) => button_show && add_item\(\)"/)
	assert.match(source, /can_edit = computed\(\(\) => docstatus\.value === 0/)
})
