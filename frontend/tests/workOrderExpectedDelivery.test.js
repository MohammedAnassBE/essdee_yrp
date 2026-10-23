import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

import { applyPlannedEndDate } from "../src/departments/fabric-store/workOrderDates.js"

const editor = fs.readFileSync(new URL("../src/departments/fabric-store/WorkOrderEditor.vue", import.meta.url), "utf8")

test("Planned end fills an empty expected delivery date", () => {
	const form = { planned_end_date: "", expected_delivery_date: "" }
	applyPlannedEndDate(form, "2026-11-10")
	assert.deepEqual(form, { planned_end_date: "2026-11-10", expected_delivery_date: "2026-11-10" })
})

test("Expected delivery keeps following the planned end until overridden", () => {
	const form = { planned_end_date: "2026-11-10", expected_delivery_date: "2026-11-10" }
	applyPlannedEndDate(form, "2026-11-12")
	assert.equal(form.expected_delivery_date, "2026-11-12")
	form.expected_delivery_date = "2026-11-20"
	applyPlannedEndDate(form, "2026-11-15")
	assert.deepEqual(form, { planned_end_date: "2026-11-15", expected_delivery_date: "2026-11-20" })
})

test("Work Order editor routes planned end changes through the sync", () => {
	assert.match(editor, /:model-value="form\.planned_end_date"[^>]*@update:model-value="changePlannedEndDate"/)
	assert.match(editor, /function changePlannedEndDate\(value\) \{ applyPlannedEndDate\(form, value\); markDirty\(\) \}/)
})
