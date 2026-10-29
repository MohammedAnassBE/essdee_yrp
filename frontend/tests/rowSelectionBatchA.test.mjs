import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { reactive } from "vue"

import { useRowSelection } from "../src/components/common/childGrid/rowSelection.js"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script setup>"))

test("item attributes select rows by key and delete through removeAttribute", () => {
	const source = read("departments/purchase/ItemEditorPage.vue")
	const template = templateOf(source)
	assert.doesNotMatch(template, /Remove attribute/)
	assert.match(template, /<input v-if="canEditAttributes" type="checkbox" class="attribute-checkbox" data-row-select tabindex="-1" :checked="attributeSelection\.isSelected\(row\.key\)"/)
	assert.match(template, /data-row-select :checked="attributeSelection\.isAllSelected\.value" :indeterminate="attributeSelection\.isPartlySelected\.value"/)
	assert.match(template, /<footer v-if="attributeSelection\.selected\.value\.length" class="attribute-selection">/)
	assert.match(template, /label="Delete"[^>]*:disabled="formDisabled" @click="deleteSelectedAttributes"/)
	assert.match(source, /canEditAttributes\.value && !formDisabled\.value \? form\.attributes\.map\(\(row\) => row\.key\) : \[\]/)
	assert.match(source, /removeAttribute\(form\.attributes\.findIndex\(\(row\) => row\.key === key\)\), \(\) => !formDisabled\.value/)
})

test("item attributes show the empty note only when there are no attribute rows, not whenever none are selected", () => {
	const template = templateOf(read("departments/purchase/ItemEditorPage.vue"))
	assert.match(template, /<div v-if="!form\.attributes\.length" class="attribute-empty">/)
	assert.doesNotMatch(template, /<\/footer>\s*<div v-else class="attribute-empty">/)
})

test("item attribute delete removes selected rows and clears dropped primary and dependent attributes", async () => {
	const form = reactive({ attributes: [{ key: "a", attribute: "Colour" }, { key: "b", attribute: "Size" }, { key: "c", attribute: "Style" }], primary_attribute: "Size", dependent_attribute: "Style" })
	const selection = useRowSelection(() => form.attributes.map((row) => row.key))
	const removeAttribute = (index) => {
		form.attributes.splice(index, 1)
		const names = new Set(form.attributes.map((row) => row.attribute))
		if (!names.has(form.primary_attribute)) form.primary_attribute = ""
		if (!names.has(form.dependent_attribute)) form.dependent_attribute = ""
	}
	selection.toggle("b", true)
	selection.toggle("c", true)
	await selection.removeSelected((key) => removeAttribute(form.attributes.findIndex((row) => row.key === key)))
	assert.deepEqual(form.attributes.map((row) => row.key), ["a"])
	assert.equal(form.primary_attribute, "")
	assert.equal(form.dependent_attribute, "")
	assert.deepEqual(selection.selected.value, [])
})

test("item child grids remove rows through the shared checkbox grid, keeping the default UOM row", () => {
	for (const path of ["ItemAdditionalParameters", "ItemUomConversions", "ItemYarnRatio"]) {
		const source = read(`departments/purchase/item/${path}.vue`)
		assert.match(source, /<ChildGridTable [^>]*:remove-row="editable && !disabled \?/)
		assert.doesNotMatch(source, /pi-trash/)
	}
	assert.match(read("departments/purchase/item/ItemUomConversions.vue"), /:can-remove-row="\(row\) => !isDefaultRow\(row\)"/)
})

test("purchase invoice, bill tracking and item price pages have no editable child row removal", () => {
	for (const path of ["accounts/PurchaseInvoiceEditorPage.vue", "accounts/PurchaseInvoice.vue", "hr/BillTrackingEditorPage.vue", "hr/BillTracking.vue", "purchase/ItemPricePage.vue"]) {
		assert.doesNotMatch(templateOf(read(`departments/${path}`)), /Remove row|aria-label="`Remove/)
	}
})
