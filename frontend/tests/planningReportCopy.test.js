import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
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
		assert.doesNotMatch(text, /useIncrementalRows|virtualScroller|paginator/, `${name} must mount every row for the copy`)
	}
	const table = source("PlanningReportTable.vue")
	assert.doesNotMatch(table, /useIncrementalRows|virtualScroller|paginator/)
	assert.match(table, /class="finishing-scroll planning-report-scroll"/, "the only clipping box is the scroll frame the copy expands")
})

test("PlanningReportTable mounts every row and column of a long, wide report", async (context) => {
	const component = loadComponent(new URL("../src/departments/planning/reports/PlanningReportTable.vue", import.meta.url).pathname, { "vue-router": { RouterLink: () => null }, "../../../composables/useInlineFilters.js": inlineFilters })
	for (const [label, props] of [["plain", {}], ["inline filters", { inlineFilters: true }], ["block spans", { cellSpan: blockCellSpan(blockSpans(rows)) }]]) {
		await context.test(label, () => {
			const root = mountComponent(component, { title: "T", columns, rows, cellAlign: () => "", formattedCell: (column, row) => String(row[column.fieldname]), ...props })
			try {
				const bodyRows = findNodes(root, (node) => node.type === "tbody")[0].children.filter((child) => child.type === "tr")
				assert.equal(bodyRows.length, rows.length)
				assert.equal(findNodes(root, (node) => node.type === "col").length, columns.length)
				assert.equal(bodyRows.at(-1).children.filter((child) => child.type === "td").length, columns.length)
			} finally { root.__vue_app__.unmount() }
		})
	}
})
