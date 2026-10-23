import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { formatReportCell } from "../src/departments/finishing/reports/finishingReports.js"

const read = (file) => readFileSync(new URL(`../src/departments/finishing/${file}`, import.meta.url), "utf8")

test("finishing report cells show Date and Datetime columns as DD-MM-YYYY", () => {
	assert.equal(formatReportCell({ fieldname: "date", fieldtype: "Date" }, { date: "2026-10-23" }), "23-10-2026")
	assert.equal(formatReportCell({ fieldname: "at", fieldtype: "Datetime" }, { at: "2026-10-23 14:05:09.123" }), "23-10-2026 14:05")
	assert.equal(formatReportCell({ fieldname: "lot", fieldtype: "Link" }, { lot: "2026-10-23" }), "2026-10-23")
	assert.equal(formatReportCell({ fieldname: "date", fieldtype: "Date" }, { date: "" }), "")
})

test("finishing entry and document timestamps render through the shared date helper", () => {
	assert.match(read("components/FinishingLinkedDocuments.vue"), /\{\{ formatDisplayDatetime\(document\.date, \{ seconds: true \}\) \}\}/)
	assert.match(read("plan/FinishingSourceEntries.vue"), /\{\{ formatDisplayDatetime\(entry\.date, \{ seconds: true \}\) \}\}/)
	assert.match(read("plan/FinishingProfitAndLossTab.vue"), /\{\{ formatDisplayDatetime\(document\.modified, \{ seconds: true \}\) \}\}/)
})
