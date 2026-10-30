import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import test from "node:test"

const finishing = path.resolve(import.meta.dirname, "../src/departments/finishing")
const read = (file) => fs.readFileSync(path.join(finishing, file), "utf8")
const fieldTag = (source, field) => source.split("\n").find((line) => line.includes(`field === '${field}'`)) || ""

test("entry dialog target lot uses the shared lot link search scoped to alternate lots", () => {
	const tag = fieldTag(read("FinishingEntryDialog.vue"), "target_lot")
	assert.match(tag, /<LinkField /)
	assert.match(tag, /doctype="SD YRP Lot"/)
	assert.match(tag, /:filters="\{ name: \['in', options\.alternate_lots \|\| \[\]\] \}"/)
	assert.match(tag, /:allow-create="false"/)
})

test("entry dialog alternative item uses the shared item link search scoped to alternatives", () => {
	const source = read("FinishingEntryDialog.vue")
	const tag = fieldTag(source, "alternative_item")
	assert.match(tag, /<LinkField /)
	assert.match(tag, /doctype="Item"/)
	assert.match(tag, /:filters="\{ name: \['in', options\.alternative_items \|\| \[\]\] \}"/)
	assert.match(tag, /@update:model-value="setAlternativeItem"/)
	assert.match(source, /function setAlternativeItem\(item\) \{\n\tif \(\(item \|\| ""\) === form\.alternative_item\) return\n\tform\.alternative_item = item \|\| ""\n\tform\.production_detail = ""/)
})

test("finishing lot and item filters go through the shared link search", () => {
	const files = ["FinishingReworkDetails.vue", "reports/FinishingRejectionReport.vue", "reports/FinishingReworkCompletion.vue", "reports/FinishingPlanReport.vue", "reports/FinishingIroningDpr.vue", "reports/FinishingPackingDpr.vue", "reports/FinishingDispatchReport.vue"]
	for (const file of files) {
		const source = read(file)
		assert.match(source, /(LinkField|AsyncLinkMultiSelect) v-model="filters\.(lot|lots)" doctype="SD YRP Lot"/, file)
		assert.doesNotMatch(source, /search-handler|searchLink\(/, file)
		assert.doesNotMatch(source, /doctype="Item"[^>]*allow-variants/, file)
	}
})
