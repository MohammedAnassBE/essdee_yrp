import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as reportColumns from "../src/composables/reportColumns.js"
import * as incrementalRows from "../src/composables/useIncrementalRows.js"
import * as inlineFilters from "../src/composables/useInlineFilters.js"
import { blockCellSpan, blockSpans } from "../src/departments/planning/reports/inhouseQuantityBlocks.js"

const source = (name) => readFileSync(new URL(`../src/departments/planning/reports/${name}`, import.meta.url), "utf8")
const columns = Array.from({ length: 40 }, (_, index) => ({ key: `c${index}`, fieldname: `c${index}`, label: `C${index}`, width: 120 }))
const rows = Array.from({ length: 900 }, (_, index) => Object.fromEntries(columns.map((column) => [column.fieldname, index])))

test("Copy Report on planning quantity reports captures the whole shell with the table inside it", () => {
	for (const name of ["InhouseQuantityReport.vue", "InwardQuantityReport.vue", "ColourWiseDiffReport.vue"]) {
		const text = source(name)
		assert.match(text, /<ReportShell\b.*\scopyable\s/, `${name} must keep Copy Report on the shell`)
		assert.match(text, /<PlanningReportTable\b/, `${name} must render its rows through PlanningReportTable`)
		assert.doesNotMatch(text, /virtualScroller|paginator/, `${name} must mount every row for the copy`)
	}
	const table = source("PlanningReportTable.vue")
	assert.doesNotMatch(table, /virtualScroller|paginator/)
	assert.match(table, /useIncrementalRows\(/, "rows mount in steps; ReportShell mounts the rest before Copy Report or a rendered export")
	assert.match(table, /class="finishing-scroll planning-report-scroll"/, "the only clipping box is the scroll frame the copy expands")
})

const tableModules = { "vue-router": { RouterLink: () => null }, "primevue/button": (props) => Vue.h("button", props), "../../../composables/useIncrementalRows.js": incrementalRows, "../../../composables/useInlineFilters.js": inlineFilters, "../../../composables/reportColumns.js": reportColumns }
const bodyRows = (root) => findNodes(root, (node) => node.type === "tbody")[0].children.filter((child) => child.type === "tr" && child.props.class !== "planning-report-more")
const moreRow = (root) => findNodes(root, (node) => node.type === "tr" && node.props.class === "planning-report-more")[0]

test("PlanningReportTable mounts a long report in steps and every row inside a full-render owner", async (context) => {
	const component = loadComponent(new URL("../src/departments/planning/reports/PlanningReportTable.vue", import.meta.url).pathname, tableModules)
	for (const [label, props] of [["plain", {}], ["inline filters", { inlineFilters: true }]]) {
		await context.test(label, async () => {
			let renderAll
			const owner = { setup: () => { renderAll = incrementalRows.provideFullRender(); return () => Vue.h(component, { title: "T", columns, rows, cellAlign: () => "", formattedCell: (column, row) => String(row[column.fieldname]), ...props }) } }
			const root = mountComponent(owner)
			try {
				assert.equal(bodyRows(root).length, incrementalRows.ROW_RENDER_STEP)
				assert.ok("data-export-ignore" in moreRow(root).props, "a rendered export skips the Show more row")
				assert.equal(findNodes(moreRow(root), (node) => node.type === "td")[0].props.colspan, columns.length)
				await renderAll()
				assert.equal(bodyRows(root).length, rows.length)
				assert.equal(moreRow(root), undefined)
				assert.equal(findNodes(root, (node) => node.type === "col").length, columns.length)
				assert.equal(bodyRows(root).at(-1).children.filter((child) => child.type === "td").length, columns.length)
			} finally { root.__vue_app__.unmount() }
		})
	}
})

test("PlanningReportTable block layouts mount every row so no rowspan block is cut", () => {
	const component = loadComponent(new URL("../src/departments/planning/reports/PlanningReportTable.vue", import.meta.url).pathname, tableModules)
	const root = mountComponent(component, { title: "T", columns, rows, cellAlign: () => "", formattedCell: (column, row) => String(row[column.fieldname]), cellSpan: blockCellSpan(blockSpans(rows)) })
	try {
		assert.equal(bodyRows(root).length, rows.length)
		assert.equal(moreRow(root), undefined)
	} finally { root.__vue_app__.unmount() }
})

test("PlanningReportTable types cells for the shared report table styles and marks block starts", () => {
	const component = loadComponent(new URL("../src/departments/planning/reports/PlanningReportTable.vue", import.meta.url).pathname, tableModules)
	const typed = [{ key: "number", fieldname: "number", label: "S.No", fieldtype: "Int" }, { key: "colour", fieldname: "colour", label: "Colour", fieldtype: "Data" }, { key: "type", fieldname: "type", label: "Type", fieldtype: "Data" }, { key: "first_date", fieldname: "first_date", label: "First Date", fieldtype: "Date" }]
	const blockRows = [1, 1, 1, 2, 3, 3].map((number, index) => ({ number, colour: "Red", type: `T${index}`, first_date: "2025-06-03" }))
	const spans = blockSpans(blockRows)
	const root = mountComponent(component, { title: "T", columns: typed, rows: blockRows, cellAlign: () => "", formattedCell: (column, row) => String(row[column.fieldname]), cellSpan: blockCellSpan(spans) })
	try {
		const table = findNodes(root, (node) => node.type === "table")[0]
		assert.match(table.props.class, /\breport-table\b/)
		const headers = findNodes(root, (node) => node.type === "th").map((node) => node.props.class)
		assert.deepEqual(headers.map((name) => name.match(/report-cell--\w+/)[0]), ["report-cell--num", "report-cell--text", "report-cell--text", "report-cell--date"])
		const starts = bodyRows(root).map((row) => /report-group-start/.test(row.props.class || ""))
		assert.deepEqual(starts, [false, false, false, true, true, false])
	} finally { root.__vue_app__.unmount() }
})

test("Report table styles load globally, not with the first Finishing page", () => {
	const read = (name) => readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8")
	assert.match(read("main.js"), /import "\.\/styles\/reportTables\.css"/)
	assert.match(read("styles/reportTables.css"), /:is\(\.finishing-table, \.report-table\) thead th \{[^}]*background: var\(--erp-surface-muted\)/)
	assert.doesNotMatch(read("departments/finishing/finishing.css"), /\.finishing-table|\.finishing-scroll/, "one owner for the table base")
})
