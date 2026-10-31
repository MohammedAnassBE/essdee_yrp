import test from "node:test"
import assert from "node:assert/strict"
import { planBadge } from "../src/departments/purchase/lot/lotViews.js"
import { formatReportCell } from "../src/departments/finishing/reports/finishingReports.js"

test("planning plan badge shows the build date as DD-MM-YYYY", () => {
	assert.equal(planBadge({ plan_status: "Built", plan_built_on: "2026-10-23 14:05:09.123456" }).text, "Plan ready 23-10-2026")
	assert.equal(planBadge({ plan_status: "Built" }).text, "Plan ready ")
})

test("planning report cells show Date and Datetime columns as DD-MM-YYYY", () => {
	assert.equal(formatReportCell({ fieldname: "first_date", fieldtype: "Date" }, { first_date: "2026-10-23" }), "23-10-2026")
	assert.equal(formatReportCell({ fieldname: "at", fieldtype: "Datetime" }, { at: "2026-10-23 14:05:09" }), "23-10-2026 14:05")
	assert.equal(formatReportCell({ fieldname: "first_date", fieldtype: "Date" }, { first_date: "" }), "")
	assert.equal(formatReportCell({ fieldname: "qty", fieldtype: "Int" }, { qty: 1200 }), "1,200")
	assert.equal(formatReportCell({ fieldname: "lot", fieldtype: "Link" }, { lot: "LOT-2026-10-23" }), "LOT-2026-10-23")
})
