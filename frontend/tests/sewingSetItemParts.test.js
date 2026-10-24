import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { sewingColourNames, sewingColourParts, sewingPartLabel } from "../src/departments/sewing/setItemParts.js"

const colours = { "Navy": { part: "Top" }, "Navy (Navy)": { part: "Bottom" }, "Red": { part: "Top" } }

test("Sewing set-item parts list each part once in row order", () => {
	assert.deepEqual(sewingColourParts(colours), ["Top", "Bottom"])
	assert.deepEqual(sewingColourParts({ Navy: { part: null } }), [])
})

test("Sewing part column uses the IPD set item attribute and hides for non-set items", () => {
	assert.equal(sewingPartLabel({ is_set_item: 1, set_attr: "Part" }, colours), "Part")
	assert.equal(sewingPartLabel({ is_set_item: 1, set_attr: "" }, {}), "Part")
	assert.equal(sewingPartLabel({}, colours), "Part")
	assert.equal(sewingPartLabel({ is_set_item: 0 }, { Navy: { part: null } }), "")
})

test("Sewing quantity matrix renders the part as its own column", () => {
	const source = fs.readFileSync(new URL("../src/departments/sewing/components/SewingQuantityMatrix.vue", import.meta.url), "utf8")
	assert.match(source, /<th v-if="partHeader" scope="col"[^>]*>\{\{ partHeader \}\}<\/th>/)
	assert.match(source, /sewing-quantity-matrix__part-pill">\{\{ colour\.part \}\}/)
	const entry = fs.readFileSync(new URL("../src/departments/sewing/plan/SewingDataEntry.vue", import.meta.url), "utf8")
	assert.equal(entry.match(/:part-label="sewingPartLabel\(currentPlan\.details, currentPlan\.colours\)"/g).length, 2)
})

test("Sewing Data Entry cards list colour names once in row order", () => {
	const setColours = { "Navy": { variant_colour: "Navy", part: "Top" }, "White (Navy)": { variant_colour: "White", part: "Bottom" }, "Black": { variant_colour: "Black", part: "Top" }, "Navy (Black)": { variant_colour: "Navy", part: "Bottom" } }
	assert.deepEqual(sewingColourNames(setColours), ["Navy", "White", "Black"])
	assert.deepEqual(sewingColourNames({ Red: {} }), ["Red"])
	assert.deepEqual(sewingColourNames(null), [])
	const entry = fs.readFileSync(new URL("../src/departments/sewing/plan/SewingDataEntry.vue", import.meta.url), "utf8")
	assert.match(entry, /<small>Colours<\/small><strong :title="sewingColourNames\(plan\.data\.colours\)\.join\(', '\)">\{\{ sewingColourNames\(plan\.data\.colours\)\.join\(', '\) \|\| '—' \}\}<\/strong>/)
})
