import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { formatDisplayDate, formatDisplayDatetime } from "../src/utils/dateFormat.js"

const component = (name) => readFileSync(new URL(`../src/departments/accounts/components/${name}`, import.meta.url), "utf8")

test("purchase invoice date cells use the shared DD-MM-YYYY helper", () => {
	for (const [name, call] of [
		["PurchaseInvoiceTabs.vue", "formatDisplayDate(grn.posting_date)"],
		["PurchaseInvoiceGrnPicker.vue", "formatDisplayDate(data.posting_date)"],
		["PurchaseInvoiceVerification.vue", "formatDisplayDatetime(approval.approved_time)"],
	]) {
		const source = component(name)
		assert.ok(source.includes(call), `${name} renders ${call}`)
		assert.match(source, /from "\.\.\/\.\.\/\.\.\/utils\/dateFormat\.js"/, name)
		assert.doesNotMatch(source, /function (date|dateTime|displayDate)\(/, `${name} has no local date formatter`)
	}
})

test("purchase invoice GRN and approval values render as DD-MM-YYYY", () => {
	assert.equal(formatDisplayDate("2026-10-23"), "23-10-2026")
	assert.equal(formatDisplayDate(""), "—")
	assert.equal(formatDisplayDatetime("2026-10-23 14:05:09.123456"), "23-10-2026 14:05")
})
