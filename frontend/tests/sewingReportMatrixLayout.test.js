import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

function mountMatrix(props) {
	const component = loadComponent(new URL("../src/departments/sewing/components/SewingReportMatrix.vue", import.meta.url).pathname, {
		"../../../components/reports/inlineFilters.js": { columnTotal: () => 0 },
		"../../../components/reports/ReportFilterRow.vue": Vue.defineComponent({ render: () => null }),
		"../../../composables/useInlineFilters.js": { useInlineFilters: () => ({ filteredRows: Vue.ref([]), isFiltered: Vue.ref(false) }) },
	})
	return mountComponent(component, props)
}
const classesOf = (root, type) => findNodes(root, (node) => node.type === type).map((node) => String(node.props.class || ""))

test("Sewing report matrix uses the shared report table: typed cells, unbroken short labels, a total row", () => {
	const root = mountMatrix({
		label: "Status",
		columns: [{ key: "date", label: "Input Date", fieldtype: "Date" }, { key: "colour", label: "Colour", wrap: true }, { key: "lot", label: "Lot" }, { key: "qty", label: "8-10", numeric: true }],
		rows: [{ key: "a", date: "2026-10-23", colour: "Navy", lot: "JB2627-015", qty: 4 }],
		totals: { qty: 4 },
	})
	assert.match(classesOf(root, "table")[0], /\breport-table\b/)
	const cells = classesOf(root, "td")
	assert.match(cells[0], /report-cell--date/)
	assert.match(cells[1], /report-cell--text/)
	assert.doesNotMatch(cells[2], /report-cell--text/)
	assert.match(cells[3], /report-cell--num/)
	assert.match(cells[3], /report-cell--last-column/)
	assert.doesNotMatch(cells[2], /report-cell--last-column/)
	const headers = classesOf(root, "th").slice(0, 4)
	assert.doesNotMatch(headers[0], /\bnowrap\b/)
	assert.match(headers[3], /\bnowrap\b/)
	const footer = findNodes(root, (node) => node.type === "tfoot")[0]
	assert.match(String(findNodes(footer, (node) => node.type === "tr")[0].props.class), /report-total-row/)
	root.__vue_app__.unmount()
})

test("Sewing DPR and SCR let only Item and Colour wrap", async () => {
	const { scrColumns } = await import("../src/departments/sewing/reports/sewingReportTables.js")
	const wrapping = scrColumns({ primary_values: ["8-10"] }).filter((column) => column.wrap).map((column) => column.key)
	assert.deepEqual(wrapping, ["colour"])
	const source = fs.readFileSync(new URL("../src/departments/sewing/reports/sewingReportTables.js", import.meta.url), "utf8")
	assert.match(source, /\{ key: "item", label: "Item", wrap: true \}/)
})
