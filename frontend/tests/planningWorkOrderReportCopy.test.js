import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = (name) => readFileSync(new URL(`../src/departments/planning/reports/${name}`, import.meta.url), "utf8")

test("Copy Report on Month-wise Detail, Work Order and Work Order Pending captures every mounted row and column", () => {
	for (const name of ["MonthWiseDetailReport.vue", "WorkOrderReport.vue", "WorkOrderPendingReport.vue"]) {
		const text = source(name)
		assert.match(text, /<ReportShell\b.*\scopyable\s/, `${name} must keep Copy Report on the shell`)
		assert.match(text, /<PlanningReportTable\b[^>]*:rows="(rows|group\.rows)"/, `${name} must pass its full row set to PlanningReportTable`)
		assert.doesNotMatch(text, /useIncrementalRows|virtualScroller|paginator|\.slice\(/, `${name} must mount every row for the copy`)
		assert.doesNotMatch(text, /max-height|overflow:/, `${name} must not add its own clipping box around the table`)
	}
})

test("Month-wise Detail renders one table per item so every item group is copied", () => {
	assert.match(source("MonthWiseDetailReport.vue"), /v-for="group in itemGroups"[\s\S]*<PlanningReportTable\b[^>]*:rows="group\.rows"/)
})
