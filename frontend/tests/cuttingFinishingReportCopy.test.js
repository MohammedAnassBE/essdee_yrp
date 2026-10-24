import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = path => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const LAZY_ROWS = /useIncrementalRows|virtualScroller|VirtualScroller|paginator|renderMoreRows|\.slice\(/

const reports = {
	"Daily Cut Sheet": {
		files: ["departments/cutting/reports/DailyCutSheetReport.vue"],
		rows: /v-for="\(row, rowIndex\) in group\.items \|\| \[\]"/,
	},
	"Daily Production Report": {
		files: ["departments/cutting/reports/DailyProductionReport.vue", "departments/cutting/reports/ProductionMatrix.vue"],
		rows: /v-for="\(row, rowIndex\) in group\.items \|\| \[\]"/,
	},
	"Finishing Plan Report": {
		files: ["departments/finishing/reports/FinishingPlanReport.vue", "departments/finishing/reports/FinishingReportHeading.vue"],
		rows: /v-for="\(row, index\) in inlineFilter\.filteredRows\.value"/,
	},
}

for (const [name, { files, rows }] of Object.entries(reports)) {
	test(`${name} Copy Report captures every row because all rows are mounted`, () => {
		const [report] = files
		assert.match(source(report), /<ReportShell\b[^]*?\scopyable\s[^]*?<template #filters>/)
		const all = files.map(source).join("\n")
		assert.match(all, rows)
		assert.doesNotMatch(all, LAZY_ROWS)
	})
}

test("Report-owned scroll boxes clip, so the copy helper expands them to full size", () => {
	// A fixed height on a non-clipping box would not be reset by expandForCapture and would overlap content.
	const finishingPlan = source("departments/finishing/reports/FinishingPlanReport.vue")
	assert.match(finishingPlan, /class="finishing-scroll fp-report__scroll"/)
	assert.match(source("styles/reportTables.css"), /\.finishing-scroll,[^{]*\{[^}]*overflow: auto/)
	for (const file of ["departments/cutting/reports/DailyCutSheetReport.vue", "departments/cutting/reports/DailyProductionReport.vue"]) {
		const style = source(file).split("<style scoped>")[1]
		assert.doesNotMatch(style, /(^|[\s;{])(max-)?height:\s*(?=[^\d\s])/m, file)
	}
})
