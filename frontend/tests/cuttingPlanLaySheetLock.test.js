import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

const editorSource = fs.readFileSync(new URL("../src/departments/cutting/plan/CuttingPlanEditor.vue", import.meta.url), "utf8")

function canEditFieldFor({ submitted = false, allowOnSubmit = [], locked = [] }) {
	const body = editorSource.match(/function canEditField\(fieldname\) \{[\s\S]*?\n\}/)[0]
	return new Function("fields", "submittedEditor", "allowOnSubmitFields", `${body}\nreturn canEditField`)(
		{ laysheet_locked_fields: locked },
		{ value: submitted },
		{ value: new Set(allowOnSubmit) },
	)
}

test("draft and amended plans without LaySheets can change location and manual entry", () => {
	const canEditField = canEditFieldFor({})
	assert.equal(canEditField("cutting_location"), true)
	assert.equal(canEditField("is_manual_entry"), true)
})

test("submitted plan without LaySheets edits only the allow-on-submit location", () => {
	const canEditField = canEditFieldFor({ submitted: true, allowOnSubmit: ["cutting_location"] })
	assert.equal(canEditField("cutting_location"), true)
	assert.equal(canEditField("is_manual_entry"), false)
})

test("LaySheets lock location and manual entry with a visible reason", () => {
	const canEditField = canEditFieldFor({ submitted: true, allowOnSubmit: ["cutting_location", "work_order"], locked: ["cutting_location", "is_manual_entry"] })
	assert.equal(canEditField("cutting_location"), false)
	assert.equal(canEditField("is_manual_entry"), false)
	assert.equal(canEditField("work_order"), true)
	assert.match(editorSource, /v-if="fields\.laysheet_locked_fields\.length"[^>]*>Cutting Location and Is Manual Entry are locked because LaySheets exist/)
})
