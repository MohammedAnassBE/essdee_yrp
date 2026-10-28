import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const {
	MIN_COLUMN_WIDTH, clampColumnWidth, columnLayoutStorageKey, headerGrid, moveColumnLabel, orderColumns, readColumnLayout, uniqueColumnLabels, writeColumnLayout,
} = await import("../src/components/reports/columnLayout.js")
const { deskExportArgs, defaultExportSettings } = await import("../src/components/reports/reportExport.js")

const read = path => readFileSync(new URL(path, import.meta.url), "utf8")
const columns = labels => labels.map(label => ({ key: label.toLowerCase(), label }))
const labelsOf = list => list.map(column => column.label)

function memoryStorage() {
	const values = new Map()
	return { values, getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, String(value)), removeItem: key => values.delete(key) }
}

test("column widths never drop below the minimum", () => {
	assert.equal(clampColumnWidth(5), MIN_COLUMN_WIDTH)
	assert.equal(clampColumnWidth(-80), MIN_COLUMN_WIDTH)
	assert.equal(clampColumnWidth(Number.NaN), MIN_COLUMN_WIDTH)
	assert.equal(clampColumnWidth(181.6), 182)
})

test("the layout is saved per report page and title", () => {
	assert.equal(columnLayoutStorageKey("/web/sewing/reports", "DPR"), "yrp-report-columns:/web/sewing/reports:DPR")
	assert.notEqual(columnLayoutStorageKey("/web/merch/reports", "Work In Progress"), columnLayoutStorageKey("/web/planning/reports", "Work In Progress"))
})

test("widths and order survive a write and read, and an empty layout clears the entry", () => {
	const storage = memoryStorage()
	const key = columnLayoutStorageKey("/web/sewing/reports", "DPR")
	writeColumnLayout(storage, key, { widths: { "dpr-lot": { Item: 260 } }, order: { "dpr-lot": ["Colour", "Lot"] } })
	assert.deepEqual(readColumnLayout(storage, key), { widths: { "dpr-lot": { Item: 260 } }, order: { "dpr-lot": ["Colour", "Lot"] } })
	writeColumnLayout(storage, key, { widths: {}, order: {} })
	assert.equal(storage.values.has(key), false)
})

test("blocked or corrupt storage falls back to the default layout", () => {
	const throwing = { getItem() { throw new Error("blocked") }, setItem() { throw new Error("full") }, removeItem() { throw new Error("blocked") } }
	assert.deepEqual(readColumnLayout(throwing, "key"), { widths: {}, order: {} })
	assert.doesNotThrow(() => writeColumnLayout(throwing, "key", { widths: { table: { Item: 90 } }, order: {} }))
	assert.deepEqual(readColumnLayout({ getItem: () => "{not json" }, "key"), { widths: {}, order: {} })
	assert.deepEqual(readColumnLayout(null, "key"), { widths: {}, order: {} })
})

test("a column moves to the first, a middle and the last position", () => {
	const labels = ["Lot", "Item", "Colour", "Total"]
	assert.deepEqual(moveColumnLabel(labels, "Total", 0), ["Total", "Lot", "Item", "Colour"])
	assert.deepEqual(moveColumnLabel(labels, "Colour", 0), ["Colour", "Lot", "Item", "Total"])
	assert.deepEqual(moveColumnLabel(labels, "Lot", 2), ["Item", "Lot", "Colour", "Total"])
	assert.deepEqual(moveColumnLabel(labels, "Item", 4), ["Lot", "Colour", "Total", "Item"])
	assert.deepEqual(moveColumnLabel(labels, "Item", 1), labels)
	assert.deepEqual(moveColumnLabel(labels, "Missing", 0), labels)
})

test("saved order sorts the columns and keeps new columns beside their original neighbour", () => {
	const source = columns(["Lot", "Item", "Colour", "80", "85", "Total"])
	assert.deepEqual(labelsOf(orderColumns(source, ["Total", "Colour", "Lot", "Item", "80", "85"])), ["Total", "Colour", "Lot", "Item", "80", "85"])
	assert.deepEqual(labelsOf(orderColumns(source, ["Colour", "Lot", "Item", "Total"])), ["Colour", "80", "85", "Lot", "Item", "Total"])
	assert.equal(orderColumns(source, undefined), source)
	assert.deepEqual(labelsOf(orderColumns(source, ["Gone", "Total", "Lot"])), ["Total", "Lot", "Item", "Colour", "80", "85"])
})

test("pinned columns stay first whatever the saved order", () => {
	const source = [{ label: "Item", frozen: true }, { label: "Lot", frozen: true }, { label: "Colour" }, { label: "Total" }]
	const ordered = orderColumns(source, ["Total", "Colour", "Lot"], { isPinned: column => Boolean(column.frozen) })
	assert.deepEqual(labelsOf(ordered), ["Item", "Lot", "Total", "Colour"])
})

test("repeated header labels get their own keys", () => {
	assert.deepEqual(uniqueColumnLabels(["Size", "80", "80", "Total", "80"]), ["Size", "80", "80#2", "Total", "80#3"])
})

test("the header grid places grouped and spanned header cells on their columns", () => {
	const cell = (label, colSpan = 1, rowSpan = 1) => ({ label, colSpan, rowSpan })
	const row = (cells, ignored = false) => ({ cells, hasAttribute: name => ignored && name === "data-export-ignore" })
	const { cells, columnCount } = headerGrid([
		row([cell("Item", 1, 2), cell("Sizes", 2), cell("Total", 1, 2)]),
		row([cell("80"), cell("85")]),
		row([cell("filter"), cell("filter")], true),
	])
	assert.equal(columnCount, 4)
	assert.deepEqual(cells.filter(entry => entry.span === 1).map(entry => [entry.cell.label, entry.column]), [["Item", 0], ["Total", 3], ["80", 1], ["85", 2]])
})

test("a Desk-backed export sends the columns in the viewer's order", () => {
	const source = [{ kind: "base", fieldname: "lot", label: "Lot" }, { kind: "base", fieldname: "colour", label: "Colour" }, { kind: "base", fieldname: "qty", label: "Total" }]
	const ordered = orderColumns(source, ["Total", "Colour", "Lot"])
	const args = deskExportArgs({ reportKey: "stock-balance", filters: {}, columns: ordered, appliedFilters: {} }, defaultExportSettings())
	assert.deepEqual(args.columns.map(column => column.fieldname), ["qty", "colour", "lot"])
})

test("report tables read their columns through the saved order", () => {
	for (const path of [
		"../src/departments/sewing/components/SewingReportMatrix.vue",
		"../src/departments/planning/reports/PlanningReportTable.vue",
		"../src/components/reports/DeskBackedReport.vue",
		"../src/components/reports/StockBalanceReport.vue",
		"../src/departments/cut-panel-store/CutBundleBalanceReport.vue",
		"../src/departments/finishing/reports/FinishingPlanReport.vue",
	]) {
		const source = read(path)
		assert.match(source, /useOrderedColumns\(/, path)
		assert.match(source, /data-column-order/, path)
	}
	const shell = read("../src/components/reports/ReportShell.vue")
	assert.match(shell, /provideReportColumnLayout\(props\.title, resultsRoot\)/)
	assert.match(shell, /label: "Reset columns"/)
})

test("resize handles stay out of copied images", () => {
	const controller = read("../src/components/reports/columnLayoutController.js")
	assert.match(controller, /handle\.dataset\.captureHide = ""/)
})
