import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import * as reportConfig from "../src/components/reports/deskReportConfig.js"
import * as reportExport from "../src/components/reports/reportExport.js"
import { cellAlign, cellTypeClass, reconcileReportLayout, reportCellValue } from "../src/composables/reportColumns.js"
import * as incrementalRows from "../src/composables/useIncrementalRows.js"
import * as inlineFilters from "../src/composables/useInlineFilters.js"
import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"

const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
const Button = (props) => Vue.h("button", props, props.label)
const columns = [{ fieldname: "name", label: "PO Number", fieldtype: "Data" }, { fieldname: "qty", label: "Qty", fieldtype: "Float" }]
const poRows = (count) => Array.from({ length: count }, (_, index) => ({ name: `PO-${index}`, qty: index }))

function mountReport(sourceRows, reportKey = "purchase-order-itemwise") {
	const sourceColumns = Vue.ref(columns)
	const report = loadComponent(resolve("frontend/src/components/reports/DeskBackedReport.vue"), {
		"vue-router": { useRoute: () => ({ query: {} }) },
		"primevue/button": Button, "primevue/checkbox": () => null, "primevue/inputnumber": () => null, "primevue/select": () => null,
		"../common/DateField.vue": stub("date-field"), "../common/LinkField.vue": stub("link-field"),
		"./ReportShell.vue": (props, { slots }) => Vue.h("report-shell", props, [slots.default?.()]),
		"./ReportColumnPicker.vue": () => null, "./ReportRunStatus.vue": () => null,
		"./deskReportConfig.js": reportConfig, "../../composables/useIncrementalRows.js": incrementalRows, "../../composables/useInlineFilters.js": inlineFilters, "./reportExport.js": reportExport,
		"./reportUtils.js": { todayIso: () => "2026-10-22", stockCellValue: (value) => value },
		"../../composables/useWebReport.js": { useWebReport: () => ({ sourceColumns, sourceRows, activeFilters: Vue.ref(null), filtersChanged() {}, generate: async () => {} }) },
		"../../composables/useReportColumns.js": { useReportColumns: () => {
			const displayColumns = Vue.computed(() => reconcileReportLayout(sourceColumns.value, null))
			return { columns: displayColumns, displayColumns, rows: sourceRows, linkSources: Vue.ref([]), fieldsBySource: Vue.ref({}), loadLayout() {}, cellValue: reportCellValue, cellAlign }
		} },
	})
	return mountComponent(report, { reportKey })
}

const dataRows = (root) => nodes(nodes(root, "tbody")[0], "tr").filter((row) => row.props.class !== "desk-report-more")
const moreRow = (root) => nodes(root, "tr").find((row) => row.props.class === "desk-report-more")

test("Desk-backed reports mount large results in steps and keep every row reachable", async () => {
	const sourceRows = Vue.ref(poRows(27_596))
	const root = mountReport(sourceRows)
	await tick()
	assert.equal(dataRows(root).length, 200)
	assert.equal(nodes(dataRows(root)[199], "td")[0].text, "PO-199")
	assert.match(nodes(moreRow(root), "span")[0].text, /Showing 200 of 27,596 rows/)
	nodes(moreRow(root), "button")[0].props.onClick()
	await tick()
	assert.equal(dataRows(root).length, 400)
	sourceRows.value = poRows(450)
	await tick()
	assert.equal(dataRows(root).length, 200, "a new result starts from the first step again")
	for (let click = 0; click < 2; click++) {
		nodes(moreRow(root), "button")[0].props.onClick()
		await tick()
	}
	assert.equal(dataRows(root).length, 450)
	assert.equal(moreRow(root), undefined)
})

test("Desk-backed reports mount the next step when the end of the table scrolls into view", async () => {
	const observers = []
	globalThis.IntersectionObserver = class {
		constructor(callback) { this.callback = callback; this.targets = []; observers.push(this) }
		observe(target) { this.targets.push(target) }
		unobserve(target) { this.targets = this.targets.filter((item) => item !== target) }
		disconnect() { this.targets = [] }
	}
	try {
		const root = mountReport(Vue.ref(poRows(500)))
		await tick()
		assert.equal(observers.length, 1)
		const [observer] = observers
		assert.equal(observer.targets.length, 1)
		assert.ok(Vue.toRaw(observer.targets[0]) === moreRow(root))
		await observer.callback([{ isIntersecting: false }])
		assert.equal(dataRows(root).length, 200)
		await observer.callback([{ isIntersecting: true }])
		await tick()
		assert.equal(dataRows(root).length, 400)
		assert.equal(observer.targets.length, 1)
		assert.ok(Vue.toRaw(observer.targets[0]) === moreRow(root), "the sentinel is observed again after each step")
	} finally {
		delete globalThis.IntersectionObserver
	}
})

test("Rendered-export reports keep every row mounted because their export reads the table", async () => {
	const root = mountReport(Vue.ref(poRows(450)), "finishing-inward-updates")
	await tick()
	assert.equal(dataRows(root).length, 450)
	assert.equal(moreRow(root), undefined)
})

test("Desk-backed column filters narrow the full result, rebuild the total row and export only the matching rows", async () => {
	const rows = [...poRows(1_000), { name: "", qty: 499_500, is_total_row: true }]
	const root = mountReport(Vue.ref(rows))
	await tick()
	const inputs = nodes(nodes(root, "thead")[0], "input")
	assert.deepEqual(inputs.map((input) => input.props["aria-label"]), ["Filter PO Number", "Filter Qty"])
	typeInto(inputs[1], ">900")
	await tick()
	assert.equal(dataRows(root).length, 200, "typing waits for the pause before re-rendering")
	await new Promise((done) => setTimeout(done, 300))
	await tick()
	const shown = dataRows(root)
	assert.equal(shown.length, 100)
	assert.equal(nodes(shown[0], "td")[0].text, "PO-901", "rows beyond the first mounted step are found")
	const total = shown.at(-1)
	assert.match(String(total.props.class), /report-total-row/)
	assert.deepEqual(nodes(total, "td").map((cell) => cell.text), ["Total", String(Array.from({ length: 99 }, (_, index) => 901 + index).reduce((sum, value) => sum + value))])
	const exportSource = nodes(root, "report-shell")[0].props["export-source"]
	assert.equal(exportSource.desk.visibleIndices.length, 99)
	assert.equal(exportSource.desk.visibleIndices[0], 901)
	typeInto(inputs[0], "po-95")
	await new Promise((done) => setTimeout(done, 300))
	await tick()
	assert.deepEqual(dataRows(root).slice(0, -1).map((row) => nodes(row, "td")[0].text), Array.from({ length: 10 }, (_, index) => `PO-95${index}`), "filters combine with AND")
	typeInto(inputs[0], "")
	typeInto(inputs[1], "")
	await new Promise((done) => setTimeout(done, 300))
	await tick()
	assert.equal(dataRows(root).length, 200)
	assert.equal(nodes(root, "report-shell")[0].props["export-source"].desk.visibleIndices, null)
})

test("Desk-backed report tables use the shared report table cell classes", async () => {
	const root = mountReport(Vue.ref(poRows(3)))
	await tick()
	assert.match(nodes(root, "table")[0].props.class, /\breport-table\b/)
	const [nameHead, qtyHead] = nodes(nodes(root, "thead")[0], "th")
	assert.match(nameHead.props.class, /report-cell--id/)
	assert.match(qtyHead.props.class, /report-cell--num/)
	const [nameCell, qtyCell] = nodes(dataRows(root)[0], "td")
	assert.match(nameCell.props.class, /report-cell--id/)
	assert.doesNotMatch(nameCell.props.class, /report-cell--last-column/)
	assert.match(qtyCell.props.class, /report-cell--num.*report-cell--last-column/)
})

test("Report cells keep document IDs, numbers and dates on one line and let prose wrap", () => {
	const kind = (column) => cellTypeClass(column)
	assert.equal(kind({ fieldname: "lot", fieldtype: "Link", options: "SD YRP Lot" }), "report-cell--id")
	assert.equal(kind({ fieldname: "lot", fieldtype: "Data" }), "report-cell--id")
	assert.equal(kind({ fieldname: "grn", fieldtype: "Link", options: "Goods Received Note" }), "report-cell--id")
	assert.equal(kind({ fieldname: "voucher", fieldtype: "Dynamic Link", options: "voucher_type" }), "report-cell--id")
	assert.equal(kind({ fieldname: "name", fieldtype: "Data" }), "report-cell--id")
	assert.equal(kind({ fieldname: "item", fieldtype: "Link", options: "Item" }), "report-cell--text")
	assert.equal(kind({ fieldname: "supplier", fieldtype: "Link", options: "Supplier" }), "report-cell--text")
	assert.equal(kind({ fieldname: "item_name", fieldtype: "Data" }), "report-cell--text")
	assert.equal(kind({ fieldname: "qty", fieldtype: "Float" }), "report-cell--num")
	assert.equal(kind({ fieldname: "posting_date", fieldtype: "Date" }), "report-cell--date")
})

test("Desk report text cells wrap within a max width and filter inputs do not widen columns", async () => {
	const { readFileSync } = await import("node:fs")
	const desk = readFileSync(resolve("frontend/src/components/reports/DeskBackedReport.vue"), "utf8")
	assert.match(desk, /\.desk-report-table td\.report-cell--text \{ max-width: 18rem; white-space: pre-line; \}/)
	const css = readFileSync(resolve("frontend/src/styles/reportTables.css"), "utf8")
	assert.match(css, /td\.report-cell--id \{[^}]*white-space: nowrap/)
	assert.match(css, /\.report-table \.report-filter-row__input \{\s*width: 0;\s*min-width: max\(100%, 48px\);/)
})
