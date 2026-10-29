import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../../essdee_yrp/public/js/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script"))
const HELPER = 'from "yrp/public/js/utils/entryGrid.js"'

test("lay sheet cloths select manual bundles and cloth rows, add bundles on Enter and submit the cloth form", () => {
	const source = read("CuttingLaySheet/components/LaySheetCloths.vue")
	const template = templateOf(source)
	assert.ok(source.includes(HELPER))
	assert.doesNotMatch(template, /icon\('delete'|delete_group_item\(item\)|delete_item\(idx\)/)
	assert.equal(template.match(/<th v-if="!is_read_only" class="row-select">/g).length, 2)
	assert.equal(template.match(/data-row-select tabindex="-1"/g).length, 2)
	assert.match(template, /v-entry-table="\{ add: is_read_only \? null : add_manual_item, isRowBlank: is_manual_row_blank, fixed: false \}"/)
	assert.match(template, /@delete="delete_selected_manual_items"/)
	assert.match(template, /@delete="delete_selected_cloth_items"/)
	assert.match(template, /v-enter-submits="submit_form"/)
	assert.match(source, /is_read_only = computed\(\(\) => locked_status\.value \|\| cur_frm\.doc\.docstatus > 0 \|\| !cur_frm\.has_perm\("write"\)\)/)
	assert.match(source, /cloth_selection\.removeSelected\(delete_item, /)
})

test("lay sheet accessories select rows, delete through delete_item and submit the accessory form on Enter", () => {
	const source = read("CuttingLaySheet/components/LaySheetAccessory.vue")
	const template = templateOf(source)
	assert.ok(source.includes(HELPER))
	assert.doesNotMatch(template, /icon\('delete'/)
	assert.match(template, /<th v-if="!is_read_only" class="row-select"><input type="checkbox" data-row-select/)
	assert.match(template, /<td v-if="!is_read_only" class="row-select"><input type="checkbox" data-row-select tabindex="-1"/)
	assert.match(template, /v-enter-submits="submit_form"/)
	assert.match(source, /selection\.removeSelected\(delete_item, \(\) => !is_read_only\.value\)/)
})

test("cutting marker groups select and delete through delete_group_item only while editable", () => {
	const source = read("Cutting_Marker/components/cutting_marker.vue")
	const template = templateOf(source)
	assert.ok(source.includes(HELPER))
	assert.doesNotMatch(template, /icon\('delete'/)
	assert.match(template, /<td v-if="can_delete_groups" class="row-select"><input type="checkbox" data-row-select tabindex="-1"/)
	assert.match(template, /<SelectionFooter :count="group_selection\.selected\.value\.length" @delete="delete_selected_groups" \/>/)
	assert.match(source, /can_delete_groups = computed\(\(\) => docstatus\.value == 0 && cur_frm\.has_perm\("write"\)\)/)
	assert.match(source, /delete_group_item\(grp_items\.value\[index\]\)/)
})

test("recut and print panel dialog selects rows and submits its add form on Enter", () => {
	const source = read("CuttingPlan/components/RecutPrintPanelDetails.vue")
	const template = templateOf(source)
	assert.ok(source.includes(HELPER))
	assert.doesNotMatch(template, /icon\('delete'|<th>Delete<\/th>/)
	assert.match(template, /data-row-select tabindex="-1"/)
	assert.match(template, /v-enter-submits="submit_form"/)
	assert.match(source, /selection\.removeSelected\(delete_item\)/)
})

test("cutting order cloth detail adds rows on Enter, keeps Enter-to-pick dia and deletes selected rows", () => {
	const source = read("CuttingOrder/ClothDetail.vue")
	const template = templateOf(source)
	assert.ok(source.includes(HELPER))
	assert.doesNotMatch(template, /icon\('delete'|selectFirst/)
	assert.match(template, /<div @keydown\.capture="select_typed_dia">/)
	assert.match(template, /v-entry-table="\{ add: is_read_only \? null : add_row, isRowBlank: is_row_blank, fixed: false \}"/)
	assert.match(template, /<td v-if="!is_read_only" class="row-select"><input type="checkbox" data-row-select tabindex="-1"/)
	assert.match(source, /selection\.removeSelected\(delete_row, \(\) => !is_read_only\.value\)/)
})
