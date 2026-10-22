import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { blockCellSpan, blockSpans } from "../src/departments/planning/reports/inhouseQuantityBlocks.js"
import * as inlineFilters from "../src/composables/useInlineFilters.js"

const types = ["Delivered", "Received", "Difference"]
const block = (number, colour, supplier, part = "") => types.map((type) => ({ number, colour, part, supplier, type, size_0: 1, total: 1, diff: 4 }))
const footer = (part) => types.map((type) => ({ colour: "Total", part, type, size_0: 2, total: 2, is_total_row: true }))
const rows = [...block(1, "Red", "Unit A", "Top"), ...block(2, "Red", "Unit B", "Top"), ...block(3, "Blue", "Unit A", "Bottom"), ...footer("Bottom"), ...footer("Top")]
const columns = ["number", "colour", "part", "supplier", "type", "size_0", "total", "first_date", "last_date", "diff"].map((fieldname) => ({ key: fieldname, fieldname, label: fieldname, width: 80 }))

test("each colour/supplier block and part footer spans its three rows", () => {
	assert.deepEqual(blockSpans(rows), [3, 0, 0, 3, 0, 0, 3, 0, 0, 3, 0, 0, 3, 0, 0])
	assert.deepEqual(blockSpans([]), [])
})

test("only identity and diff columns merge across a block", () => {
	const span = blockCellSpan(blockSpans(rows))
	assert.deepEqual(columns.map((column) => span(column, rows[0], 0)), [3, 3, 3, 3, 1, 1, 1, 1, 1, 3])
	assert.deepEqual(columns.map((column) => span(column, rows[1], 1)), [0, 0, 0, 0, 1, 1, 1, 1, 1, 0])
})

test("table renders supplier and colour once per block", () => {
	const table = loadComponent(new URL("../src/departments/planning/reports/PlanningReportTable.vue", import.meta.url).pathname, { "vue-router": { RouterLink: (_props, { slots }) => Vue.h("a", slots.default?.()) }, "../../../composables/useInlineFilters.js": inlineFilters })
	const root = mountComponent(table, { title: "In-house Quantity", columns, rows, cellAlign: () => "", formattedCell: (column, row) => String(row[column.fieldname] ?? ""), cellSpan: blockCellSpan(blockSpans(rows)) })
	try {
		const bodyRows = findNodes(root, (node) => node.type === "tr").slice(1)
		const cells = (tr) => tr.children.filter((child) => child.type === "td")
		const text = (td) => findNodes(td, (node) => node.type === "text").map((node) => node.text).join("")
		assert.equal(bodyRows.length, 15)
		assert.deepEqual(bodyRows.map((tr) => cells(tr).length), [10, 5, 5, 10, 5, 5, 10, 5, 5, 10, 5, 5, 10, 5, 5])
		assert.deepEqual(cells(bodyRows[0]).slice(0, 4).map(text), ["1", "Red", "Top", "Unit A"])
		assert.equal(cells(bodyRows[0])[0].props.rowspan, 3)
		assert.deepEqual(cells(bodyRows[1]).map(text), ["Received", "1", "1", "", ""])
		const sticky = (td) => JSON.stringify(td.props.class).includes("planning-report-first")
		assert.ok(sticky(cells(bodyRows[0])[0]))
		assert.equal(cells(bodyRows[1]).some(sticky), false, "rows inside a block must not pin their Type cell")
		const supplierCells = findNodes(root, (node) => node.type === "td" && ["Unit A", "Unit B"].includes(text(node)))
		assert.equal(supplierCells.length, 3)
	} finally { root.__vue_app__.unmount() }
})

test("tables without a span function render every cell", () => {
	const table = loadComponent(new URL("../src/departments/planning/reports/PlanningReportTable.vue", import.meta.url).pathname, { "vue-router": { RouterLink: () => null }, "../../../composables/useInlineFilters.js": inlineFilters })
	const root = mountComponent(table, { title: "T", columns, rows: rows.slice(0, 3), cellAlign: () => "", formattedCell: () => "x" })
	try {
		const tds = findNodes(root, (node) => node.type === "td")
		assert.equal(tds.length, 30)
		assert.ok(tds.every((td) => td.props.rowspan === undefined))
	} finally { root.__vue_app__.unmount() }
})
