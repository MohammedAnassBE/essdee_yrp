import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"
import * as inlineFilterComposable from "../src/composables/useInlineFilters.js"
import * as incrementalRows from "../src/composables/useIncrementalRows.js"
import * as reportColumns from "../src/composables/reportColumns.js"
import * as inlineFilterHelpers from "../src/components/reports/inlineFilters.js"
import { columnTotal, createRowFilter, filteredTotalRow, guessFilter, splitTotalRow } from "../src/components/reports/inlineFilters.js"
import { tableGrid } from "../src/components/reports/reportExport.js"
import { INLINE_FILTER_DELAY, useInlineFilters } from "../src/composables/useInlineFilters.js"

const columns = [
	{ key: "base:item", fieldname: "item", label: "Item", fieldtype: "Link" },
	{ key: "base:qty", fieldname: "qty", label: "Qty", fieldtype: "Float" },
	{ key: "base:boxes", fieldname: "boxes", label: "Boxes", fieldtype: "Int" },
	{ key: "base:share", fieldname: "share", label: "Share", fieldtype: "Percent" },
]
const rows = [
	{ item: "Blue Tee", qty: 50, boxes: 2, share: 10 },
	{ item: "RED Polo", qty: 150, boxes: 3, share: 30 },
	{ item: "Red Tee", qty: 1234.5, boxes: 5, share: 20 },
	{ item: "Green Cap", qty: null, boxes: 0, share: 40 },
]
const cellValue = (row, column) => row[column.fieldname]
const cellText = (row, column) => column.fieldtype === "Float" ? Number(row.qty).toLocaleString("en-IN", { minimumFractionDigits: 3 }) : String(row[column.fieldname])
const matching = (keywords) => createRowFilter(rows, columns, { cellValue, cellText }).getMatchingIndices(keywords)

test("inline filter keywords parse like frappe-datatable's guessFilter", () => {
	assert.equal(guessFilter(""), null)
	assert.deepEqual(guessFilter("Tee"), { type: "contains", text: "tee" })
	assert.deepEqual(guessFilter(">100"), { type: "greaterThan", text: "100" })
	assert.deepEqual(guessFilter("< 20"), { type: "lessThan", text: "20" })
	assert.deepEqual(guessFilter("=150"), { type: "equals", text: 150 })
	assert.deepEqual(guessFilter("!=150"), { type: "notEquals", text: 150 })
	assert.deepEqual(guessFilter("10:20"), { type: "range", text: ["10", "20"] })
	assert.deepEqual(guessFilter("15"), { type: "containsNumber", text: "15" })
	assert.deepEqual(guessFilter("=abc"), { type: "contains", text: "abc" })
	assert.deepEqual(guessFilter(">"), { type: "containsNumber", text: "" }, "a bare operator matches every row, as in Desk")
})

test("text filters match substrings case-insensitively on the raw and displayed values", () => {
	assert.deepEqual(matching({ "base:item": "red" }), [1, 2])
	assert.deepEqual(matching({ "base:item": "TEE" }), [0, 2])
	assert.deepEqual(matching({ "base:qty": "1,234" }), [2], "the displayed number text is searchable")
	assert.deepEqual(matching({ "base:item": "zzz" }), [])
})

test("numeric filters accept comparison operators and ranges", () => {
	assert.deepEqual(matching({ "base:qty": ">100" }), [1, 2])
	assert.deepEqual(matching({ "base:qty": "<100" }), [0, 3], "an empty cell compares as \"\" like Desk, so it is below any number")
	assert.deepEqual(matching({ "base:qty": "=150" }), [1])
	assert.deepEqual(matching({ "base:boxes": "!=0" }), [0, 1, 2])
	assert.deepEqual(matching({ "base:qty": "50:150" }), [0, 1])
	assert.deepEqual(matching({ "base:boxes": "3" }), [1], "a bare number matches the value or its text")
	assert.deepEqual(matching({ "base:qty": ">abc" }), [], "a non-numeric bound never matches a number")
})

test("several column filters combine with AND and unknown columns are ignored", () => {
	assert.deepEqual(matching({ "base:item": "tee", "base:qty": ">100" }), [2])
	assert.deepEqual(matching({ "base:item": "tee", "base:missing": "x" }), [0, 2])
})

test("totals follow Desk's report_column_total over the filtered rows", () => {
	assert.equal(columnTotal([1, "2.5", null], { fieldtype: "Float" }), 3.5)
	assert.equal(columnTotal(["2", 3.9], { fieldtype: "Int" }), 5)
	assert.equal(columnTotal([10, 30], { fieldtype: "Percent" }), 20, "Percent columns average")
	assert.equal(columnTotal([1, 2], { fieldtype: "Float", disable_total: 1 }), null)
	assert.equal(columnTotal(["a", "b"], { fieldtype: "Data" }), null)
	assert.equal(columnTotal([], { fieldtype: "Float" }), null)
	const total = filteredTotalRow([rows[1], rows[2]], columns, cellValue, { item: "", qty: 1434.5, is_total_row: true })
	assert.deepEqual(total, { item: "Total", qty: 1384.5, boxes: 8, share: 25, is_total_row: true })
})

test("only a single trailing total row is treated as the footer", () => {
	const footer = { item: "Total", is_total_row: true }
	assert.equal(splitTotalRow([...rows, footer]).totalRow, footer)
	assert.equal(splitTotalRow([...rows, footer]).dataRows.length, 4)
	const blocks = [rows[0], { is_total_row: true }, rows[1], footer]
	assert.deepEqual(splitTotalRow(blocks), { dataRows: blocks, totalRow: null })
})

test("useInlineFilters debounces typing, filters the full dataset and rebuilds the total row", async () => {
	const source = Vue.ref([...rows, { item: "Total", qty: 1434.5, boxes: 10, share: 25, is_total_row: true }])
	const scope = Vue.effectScope()
	const filter = scope.run(() => useInlineFilters(source, columns, { cellValue, cellText, delay: 20 }))
	const unfiltered = filter.filteredRows.value
	assert.equal(unfiltered, source.value, "without keywords the original rows pass through untouched")
	filter.setFilter("base:item", "r")
	filter.setFilter("base:item", "re")
	filter.setFilter("base:item", "red")
	assert.equal(filter.isFiltered.value, false, "keystrokes wait for the pause")
	await new Promise((done) => setTimeout(done, 40))
	assert.equal(filter.isFiltered.value, true)
	assert.deepEqual(filter.filteredRows.value.map((row) => row.item), ["RED Polo", "Red Tee", "Total"])
	assert.equal(filter.filteredRows.value.at(-1).qty, 1384.5)
	assert.deepEqual(filter.matchingIndices.value, [1, 2])
	assert.equal(filter.matchingCount.value, 2)
	filter.setFilter("base:qty", ">1000")
	filter.applyKeywords()
	assert.deepEqual(filter.matchingIndices.value, [2], "Enter applies without waiting")
	filter.clearFilters()
	assert.equal(filter.filteredRows.value, source.value)
	assert.equal(filter.matchingIndices.value, null)
	scope.stop()
	assert.ok(INLINE_FILTER_DELAY >= 200 && INLINE_FILTER_DELAY <= 300)
})

test("filtering 20,000 rows stays well under the frame budget", () => {
	const many = Array.from({ length: 20_000 }, (_, index) => ({ item: `Item ${index}`, qty: index % 500, boxes: index % 7, share: 1 }))
	const rowFilter = createRowFilter(many, columns, { cellValue, cellText })
	rowFilter.getMatchingIndices({ "base:item": "9", "base:qty": ">100" })
	const started = performance.now()
	const indices = rowFilter.getMatchingIndices({ "base:item": "99", "base:qty": ">100" })
	assert.ok(indices.length > 0)
	assert.ok(performance.now() - started < 50, "cached column values make repeat filters cheap")
})

test("rendered exports skip the inline filter row", () => {
	const cell = (text) => ({ textContent: text, rowSpan: 1, colSpan: 1, dataset: {} })
	const row = (cells, attributes = {}) => ({ cells, hasAttribute: (name) => name in attributes })
	const table = { rows: [row([cell("Item")]), row([cell("")], { "data-export-ignore": "" }), row([cell("Red Tee")])] }
	assert.deepEqual(tableGrid(table), [["Item"], ["Red Tee"]])
})

const nodesOf = (root, type) => findNodes(root, (node) => node.type === type)
const pause = () => new Promise((done) => setTimeout(done, INLINE_FILTER_DELAY + 50))
const bodyTexts = (root) => nodesOf(nodesOf(root, "tbody")[0], "tr").map((tr) => nodesOf(tr, "td").map((td) => findNodes(td, (node) => node.type === "text").map((node) => node.text).join("")))

test("PlanningReportTable filters only when a report opts in, so block layouts keep every row", async () => {
	const table = loadComponent(new URL("../src/departments/planning/reports/PlanningReportTable.vue", import.meta.url).pathname, { "vue-router": { RouterLink: () => null }, "primevue/button": (props) => Vue.h("button", props), "../../../composables/useIncrementalRows.js": incrementalRows, "../../../composables/useInlineFilters.js": inlineFilterComposable, "../../../composables/reportColumns.js": reportColumns })
	const props = { title: "Work Order", columns, rows, cellAlign: () => "", formattedCell: (column, row) => String(row[column.fieldname] ?? "") }
	const plain = mountComponent(table, props)
	assert.equal(nodesOf(plain, "input").length, 0)
	const root = mountComponent(table, { ...props, inlineFilters: true })
	typeInto(nodesOf(root, "input")[0], "tee")
	await pause()
	await Vue.nextTick()
	assert.deepEqual(bodyTexts(root).map((cells) => cells[0]), ["Blue Tee", "Red Tee"])
})

test("SewingReportMatrix recomputes its footer totals over the filtered rows", async () => {
	const matrix = loadComponent(new URL("../src/departments/sewing/components/SewingReportMatrix.vue", import.meta.url).pathname, {
		"../../../components/reports/inlineFilters.js": inlineFilterHelpers, "../../../composables/useInlineFilters.js": inlineFilterComposable,
	})
	const matrixColumns = [{ key: "date", label: "Date" }, { key: "polo", label: "Polo", numeric: true }]
	const matrixRows = [{ date: "01-10-2026", polo: 4 }, { date: "02-10-2026", polo: 6 }, { date: "03-10-2026", polo: 10 }]
	const root = mountComponent(matrix, { label: "Monthly", columns: matrixColumns, rows: matrixRows, totals: { polo: 20 }, totalLabel: "Grand Total", inlineFilters: true })
	const footer = () => nodesOf(nodesOf(root, "tfoot")[0], "th").map((th) => th.text || findNodes(th, (node) => node.type === "text").map((node) => node.text).join(""))
	assert.deepEqual(footer(), ["Grand Total", "20"])
	typeInto(nodesOf(root, "input")[1], ">5")
	await pause()
	await Vue.nextTick()
	assert.equal(bodyTexts(root).length, 2)
	assert.deepEqual(footer(), ["Grand Total", "16"])
})
