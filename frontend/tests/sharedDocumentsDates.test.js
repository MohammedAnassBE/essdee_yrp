import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

import { extractServerMessage } from "../src/api/errorMessages.js"
import { parseServerMessages } from "../src/api/serverMessages.js"
import { formatDisplayByFieldtype } from "../src/utils/dateFormat.js"

const source = (path) => fs.readFileSync(new URL(`../src/components/${path}`, import.meta.url), "utf8")

function formViewDisplayValue() {
	const script = source("common/FormView.vue")
	const body = script.slice(script.indexOf("function displayValue("), script.indexOf("function validate("))
	return new Function("formatDisplayByFieldtype", "plainTextFromHtml", `${body}\nreturn displayValue`)(formatDisplayByFieldtype, (value) => value)
}

test("FormView read mode shows Date and Datetime fields as DD-MM-YYYY", () => {
	const displayValue = formViewDisplayValue()
	assert.equal(displayValue("2026-10-23", { fieldtype: "Date" }), "23-10-2026")
	assert.equal(displayValue("2026-10-23 14:05:09.123456", { fieldtype: "Datetime" }), "23-10-2026 14:05")
	assert.equal(displayValue("", { fieldtype: "Date" }), "—")
	assert.equal(displayValue("2026-10-23", { fieldtype: "Data" }), "2026-10-23")
})

test("server messages, error dialogs and link descriptions format embedded dates", () => {
	const [entry] = parseServerMessages(JSON.stringify([JSON.stringify({ message: "Posting date 2026-10-23 is before PO-2026-10-23-0001" })]))
	assert.equal(entry.message, "Posting date 23-10-2026 is before PO-2026-10-23-0001")
	assert.equal(extractServerMessage({ exception: "frappe.exceptions.ValidationError: Due on 2026-10-23" }), "Due on 23-10-2026")
	assert.match(source("documents/DocumentErrorDialog.vue"), /\{\{ formatDatesInText\(message\) \}\}/)
	assert.match(source("common/LinkField.vue"), /\{\{ formatDatesInText\(option\.description\) \}\}/)
	assert.match(source("common/MultiSelectField.vue"), /\{\{ formatDatesInText\(option\.description\) \}\}/)
})
