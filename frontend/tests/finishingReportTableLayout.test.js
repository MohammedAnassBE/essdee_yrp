import assert from "node:assert/strict"
import fs from "node:fs"
import path from "node:path"
import test from "node:test"

const finishing = path.resolve(import.meta.dirname, "../src/departments/finishing")
const FILES = [
	"reports/FinishingPackingDpr.vue",
	"reports/FinishingDispatchReport.vue",
	"reports/FinishingIroningDpr.vue",
	"reports/FinishingPlanReport.vue",
	"reports/FinishingRejectionReport.vue",
	"reports/FinishingReworkCompletion.vue",
	"components/FinishingSeriesTable.vue",
	"components/FinishingReworkEntry.vue",
	"FinishingReworkGroups.vue",
]
const read = (file) => fs.readFileSync(path.join(finishing, file), "utf8")

for (const file of FILES) {
	test(`${file}: every finishing report table uses the shared report-table layout`, () => {
		const tables = read(file).match(/<table\b[^>]*>/g) || []
		assert.ok(tables.length, `${file} has a table`)
		for (const table of tables) assert.match(table, /finishing-table report-table/)
	})

	test(`${file}: numbers never wrap and the real last column keeps the frame edge`, () => {
		const source = read(file)
		assert.doesNotMatch(source, /class="erp-number(?![^"]*report-cell--num)[^"]*"/, "erp-number cells carry report-cell--num")
		assert.match(source, /report-cell--last-column/)
	})
}

test("Finishing Plan Report types body cells from the column fieldtype and keeps lots on one line", () => {
	const source = read("reports/FinishingPlanReport.vue")
	assert.match(source, /import \{ cellTypeClass \} from "..\/..\/..\/composables\/reportColumns.js"/)
	assert.match(source, /function cellClass[\s\S]*\[cellTypeClass\(column\)\]: true/)
	assert.match(source, /"report-cell--last-column": column.key === columns.value.at\(-1\)\?.key/)
	assert.match(source, /td\.fp-report__lot \{ white-space: nowrap; \}/)
})

test("Rework Completion and Ironing DPR totals use the shared total row", () => {
	for (const file of ["reports/FinishingReworkCompletion.vue", "reports/FinishingIroningDpr.vue"]) {
		assert.match(read(file), /<tr class="finishing-table__total-row report-total-row">/)
	}
})
