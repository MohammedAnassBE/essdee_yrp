import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { sizeMatrixColumns } from "../src/departments/planning/reports/productionReportFilters.js"

const source = (name) => readFileSync(new URL(`../src/departments/planning/reports/${name}`, import.meta.url), "utf8")

test("Copy Report on Dispatch Percentage, Size-wise Stock and Process Pending captures the shell with every row mounted", () => {
	for (const name of ["DispatchPercentageReport.vue", "SizeWiseStockReport.vue", "ProcessPendingReport.vue"]) {
		const text = source(name)
		assert.match(text, /<ReportShell\b.*\scopyable\s/, `${name} must keep Copy Report on the shell`)
		assert.match(text, /<PlanningReportTable\b/, `${name} must render its rows through PlanningReportTable`)
		assert.doesNotMatch(text, /useIncrementalRows|virtualScroller|paginator|\.slice\(/, `${name} must mount every row for the copy`)
	}
})

test("Size-wise Stock renders one full table per matrix inside the copied shell", () => {
	const text = source("SizeWiseStockReport.vue")
	assert.match(text, /<section v-for="matrix in matrices"[^>]*>\s*<h3>\{\{ matrix\.title \}\}<\/h3>\s*<PlanningReportTable [^>]*:rows="matrix\.rows"/)
	const columns = [
		{ fieldname: "type", label: "Type" },
		...Array.from({ length: 30 }, (_, index) => ({ fieldname: `size_${index}`, label: String(index) })),
		{ fieldname: "total", label: "Total" },
	]
	assert.equal(sizeMatrixColumns(columns, { matrix: "Style" }).length, columns.length, "every size column reaches the table")
})
