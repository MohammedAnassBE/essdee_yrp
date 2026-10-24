import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = (name) => readFileSync(new URL(`../src/departments/planning/reports/${name}`, import.meta.url), "utf8")
const tables = (text) => [...text.matchAll(/<table[\s\S]*?<\/table>/g)].map((match) => match[0])

test("Work Order Bulk Close tables use the shared report table styles with a typed class on every cell", () => {
	const bulkClose = source("WorkOrderBulkClose.vue")
	const found = tables(bulkClose)
	assert.equal(found.length, 2)
	for (const table of found) {
		assert.match(table, /<table class="finishing-table report-table">/)
		const dataCells = [...table.matchAll(/<(th|td)( [^>]*)?>(?!<input|<Button label="View")/g)].filter((cell) => !/report-filter/.test(cell[0]))
		for (const cell of dataCells) assert.match(cell[0], /report-cell--(num|date|text)/, cell[0])
	}
	assert.match(bulkClose, /report-cell--num report-align-right">\{\{ quantity\(row\.difference\) \}\}/)
	assert.match(bulkClose, /class="finishing-scroll bulk-close-scroll"/)
	assert.match(bulkClose, /<td class="report-cell--text bulk-close-id">/)
	assert.match(bulkClose, /\.finishing-table td\.bulk-close-id \{ white-space: nowrap; \}/, "Work Order IDs never break at their hyphens")
	assert.match(bulkClose, /\.bulk-close-scroll \{ max-height: 70vh; \}/, "the frame scrolls so the sticky header stays in view")
})

test("wide Planning reports give text cells room so IDs do not break at every hyphen", () => {
	for (const name of ["WorkOrderReport.vue", "WorkInProgressReport.vue"]) {
		const text = source(name)
		assert.match(text, /<section class="planning-wide-report"/, name)
		assert.match(text, /\.planning-wide-report :deep\(td\.report-cell--text\) \{ min-width: 16ch; \}/, name)
	}
})
