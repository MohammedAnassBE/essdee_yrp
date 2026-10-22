import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { mergeNames, parsePastedNames } from "../src/components/reports/pasteValues.js"
import { wipHint } from "../src/departments/planning/reports/productionReportFilters.js"

test("list paste splits on lines and tabs, trims and dedupes", () => {
	assert.deepEqual(parsePastedNames(" L-1\r\nL-2\tL-3\n\nL-1 \n"), ["L-1", "L-2", "L-3"])
	assert.deepEqual(parsePastedNames("A, B"), ["A, B"])
})

test("comma paste splits on commas only", () => {
	assert.deepEqual(parsePastedNames("L-1, L-2,,L-1 ", "comma"), ["L-1", "L-2"])
	assert.deepEqual(parsePastedNames("", "comma"), [])
})

test("pasted names merge into existing filter values without duplicates", () => {
	assert.deepEqual(mergeNames(["L-1"], ["L-1", "L-2"]), ["L-1", "L-2"])
	assert.deepEqual(mergeNames(undefined, ["L-2"]), ["L-2"])
})

test("WIP accepts a season as its only filter", () => {
	const empty = { lot: [], item: [], category: "", product_season: "" }
	assert.equal(wipHint(empty), "Select at least one Lot, Item, Category or Season.")
	assert.equal(wipHint({ ...empty, product_season: "SS26" }), "")
})

test("the five Planning reports and Merch WIP use the shared paste dialog", () => {
	const files = ["planning/reports/WorkInProgressReport.vue", "planning/reports/SizeWiseStockReport.vue", "planning/reports/MonthWiseDetailReport.vue", "planning/reports/ProcessPendingReport.vue", "cutting/reports/MultiCCRReport.vue", "merch/reports/WorkInProgressReport.vue"]
	for (const file of files) {
		const source = readFileSync(new URL(`../src/departments/${file}`, import.meta.url), "utf8")
		assert.match(source, /components\/reports\/PasteListDialog\.vue/, file)
		assert.match(source, /<PasteListDialog v-model:visible="pasteVisible" @apply="paste" \/>/, file)
	}
	const wip = readFileSync(new URL("../src/departments/planning/reports/WorkInProgressReport.vue", import.meta.url), "utf8")
	assert.match(wip, /v-model="filters\.product_season" doctype="SD YRP Product Season"/)
})
