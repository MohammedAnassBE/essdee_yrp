import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { Vue, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const text = node => [node.text, ...node.children.map(text)].join(" ")
const read = path => fs.readFileSync(new URL(path, import.meta.url), "utf8")

function mountMatrix(props) {
	const component = loadComponent(new URL("../src/departments/sewing/components/SewingReportMatrix.vue", import.meta.url).pathname, {
		"../../../components/reports/inlineFilters.js": { columnTotal: () => 0 },
		"../../../components/reports/ReportFilterRow.vue": Vue.defineComponent({ render: () => null }),
		"../../../composables/useInlineFilters.js": { useInlineFilters: () => ({ filteredRows: Vue.ref([]), isFiltered: Vue.ref(false) }) },
	})
	return mountComponent(component, props)
}

test("Sewing report matrix shows Date columns as DD-MM-YYYY and leaves other cells raw", () => {
	const root = mountMatrix({
		label: "Monthly",
		columns: [{ key: "date", label: "Date", fieldtype: "Date" }, { key: "lot", label: "Lot" }, { key: "total", label: "Total", numeric: true }],
		rows: [{ date: "2026-10-23", lot: "PO-2026-10-23", total: 1200 }, { date: null, lot: "L2", total: 0 }],
	})
	const rendered = text(root)
	assert.match(rendered, /23-10-2026/)
	assert.doesNotMatch(rendered, /(?<![-\w])2026-10-23(?![-\w])/)
	assert.match(rendered, /PO-2026-10-23/)
	root.__vue_app__.unmount()
})

test("Sewing report date columns declare the Date fieldtype", () => {
	assert.match(read("../src/departments/sewing/reports/SewingMonthlySummary.vue"), /\{ key: "date", label: "Date", fieldtype: "Date" \}/)
	assert.match(read("../src/departments/sewing/reports/SewingItemSummary.vue"), /\{ key: "date", label: "Date", fieldtype: "Date" \}/)
	assert.match(read("../src/departments/sewing/reports/SewingStatusSummary.vue"), /dateColumns = new Set\(\["FI Date", "Input Date", "Last Sewing Output"\]\)/)
})

test("Sewing Entries groups use the shared date helper", () => {
	const source = read("../src/departments/sewing/plan/SewingEntries.vue")
	assert.match(source, /<h3>\{\{ formatDisplayDate\(group\.date\) \}\}<\/h3>/)
	assert.doesNotMatch(source, /function formatDate/)
})
