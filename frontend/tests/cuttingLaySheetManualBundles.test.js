import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

import { applySetFieldDefaults, emptyManualRow, manualRowsFromSheet, manualRowsPayload, validateManualRows } from "../src/departments/cutting/laysheet/manualBundles.js"

const sizes = ["75 cm", "80 cm"]
const dialogSource = fs.readFileSync(new URL("../src/departments/cutting/CuttingLaySheetDialog.vue", import.meta.url), "utf8")
const gridSource = fs.readFileSync(new URL("../src/departments/cutting/laysheet/LaySheetManualBundles.vue", import.meta.url), "utf8")

function row(values = {}) {
	return { colour: "Navy", major_colour: "Navy", set_colour: "", shade: "A", quantity: 120, multipliers: { "75 cm": 0, "80 cm": 2 }, ...values }
}

test("a new bundle row starts like the Desk grid: quantity 1 and zero multipliers", () => {
	assert.deepEqual(emptyManualRow(sizes), { colour: "", major_colour: "", set_colour: "", shade: "", quantity: 1, multipliers: { "75 cm": 0, "80 cm": 0 } })
})

test("stored rows fill every size of the sheet", () => {
	const rows = manualRowsFromSheet({ sizes, manual_items: [{ colour: "Navy", quantity: 5, multipliers: { "80 cm": 3 } }] })
	assert.deepEqual(rows[0].multipliers, { "75 cm": 0, "80 cm": 3 })
	assert.equal(rows[0].quantity, 5)
})

test("rows are validated with the Desk messages", () => {
	const cases = [
		[row({ colour: "" }), "Bundle Row 1: Enter Colour"],
		[row({ major_colour: "" }), "Bundle Row 1: Enter Major Colour"],
		[row({ shade: "" }), "Bundle Row 1: Enter the Shade"],
		[row({ quantity: 0 }), "Bundle Row 1: Quantity should be greater than Zero"],
		[row({ multipliers: { "75 cm": -1, "80 cm": 1 } }), "Bundle Row 1: Negative Multiplier's are not Accepted"],
		[row({ multipliers: { "75 cm": 0, "80 cm": null } }), "Bundle Row 1: Enter the Multiplier for atleast one size"],
	]
	for (const [value, message] of cases) assert.equal(validateManualRows([value], { sizes }), message)
	assert.equal(validateManualRows([row()], { sizes, isSetItem: true }), "Bundle Row 1: Enter Set Colour")
	assert.equal(validateManualRows([row(), row()], { sizes }), "")
})

test("payload trims text, fills missing multipliers and sends set colour only for set items", () => {
	const payload = manualRowsPayload([row({ shade: " A ", multipliers: { "80 cm": 2 } })], { sizes })
	assert.deepEqual(payload, [{ colour: "Navy", major_colour: "Navy", shade: "A", quantity: 120, multipliers: { "75 cm": 0, "80 cm": 2 } }])
	assert.equal(manualRowsPayload([row({ set_colour: "Red" })], { sizes, isSetItem: true })[0].set_colour, "Red")
})

test("choosing a colour resets major and set colour to the marker defaults like Desk", () => {
	const value = row({ major_colour: "Old", set_colour: "Old" })
	applySetFieldDefaults(value, [{ fieldname: "major_colour", default: "Navy" }, { fieldname: "set_colour" }], true)
	assert.equal(value.major_colour, "Navy")
	assert.equal(value.set_colour, "")
})

test("manual-entry Lay Sheets show the bundle grid and save it with the cloth rows", () => {
	assert.match(dialogSource, /<LaySheetManualBundles v-if="sheet\.is_manual_entry"[^>]*:editable="canEditDetails"[^>]*@save="saveManualBundles"/)
	assert.match(dialogSource, /\.\.\.\(manualItems \? \{ manual_items: manualItems \} : \{\}\)/)
	assert.match(gridSource, /label="Save Bundles"/)
	assert.match(gridSource, /label="Add Row"/)
})
