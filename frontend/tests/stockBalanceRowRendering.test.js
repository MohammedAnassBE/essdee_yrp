import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import { FilterService } from "@primevue/core/api"
import * as reportExport from "../src/components/reports/reportExport.js"
import * as filterState from "../src/components/reports/reportFilterState.js"
import { cellAlign, reconcileReportLayout, reportCellValue } from "../src/composables/reportColumns.js"
import * as incrementalRows from "../src/composables/useIncrementalRows.js"
import * as inlineFilters from "../src/composables/useInlineFilters.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const control = (props) => Vue.h("control", props)
const Button = (props) => Vue.h("button", props, props.label)
const columns = [{ fieldname: "item", label: "Item", fieldtype: "Data" }, { fieldname: "bal_qty", label: "Balance Qty", fieldtype: "Float" }, { fieldname: "in_qty", label: "In Qty", fieldtype: "Float" }]
const stockRows = (count) => Array.from({ length: count }, (_, index) => ({ item: `ITEM-${index}`, bal_qty: 1, in_qty: 2 }))

function mountReport(sourceRows, reportColumns = columns) {
	const sourceColumns = Vue.ref(reportColumns)
	const report = loadComponent(resolve(import.meta.dirname, "../src/components/reports/StockBalanceReport.vue"), {
		"primevue/button": Button, "@primevue/core/api": { FilterService },
		"../common/DateField.vue": control, "../common/LinkField.vue": control, "../common/MultiSelectField.vue": control,
		"./ReportShell.vue": (props, { slots }) => Vue.h("report-shell", props, [slots.metrics?.(), slots.default?.()]),
		"./ReportColumnPicker.vue": control, "./ReportRunStatus.vue": control,
		"./reportExport.js": reportExport, "./reportFilterState.js": filterState,
		"./reportUtils.js": { number: (value) => String(value), oneMonthAgoIso: () => "2026-09-22", todayIso: () => "2026-10-22", stockCellValue: (value) => value },
		"../../api/frappe.js": { callMethod: async () => [], searchLink: async () => [] },
		"../../composables/useIncrementalRows.js": incrementalRows, "../../composables/useInlineFilters.js": inlineFilters,
		"../../composables/useWebReport.js": { useWebReport: () => ({ state: Vue.ref("ready"), sourceColumns, sourceRows, job: Vue.ref(null), activeFilters: Vue.ref(null), generate: async () => {}, filtersChanged() {}, clear() {} }) },
		"../../composables/useReportColumns.js": { useReportColumns: () => {
			const displayColumns = Vue.computed(() => reconcileReportLayout(sourceColumns.value, null))
			return { columns: displayColumns, displayColumns, rows: sourceRows, linkSources: Vue.ref([]), fieldsBySource: Vue.ref({}), loadLayout() {}, cellValue: reportCellValue, cellAlign }
		} },
	})
	return mountComponent(report)
}

const dataRows = (root) => nodes(nodes(root, "tbody")[0], "tr").filter((row) => row.props.class !== "stock-more")
const moreRow = (root) => nodes(root, "tr").find((row) => row.props.class === "stock-more")
const metric = (root, label) => nodes(root, "div").find((node) => nodes(node, "span")[0]?.text === label && node.children.length === 2)

test("Stock Balance mounts large results in steps while metrics cover every row", async () => {
	const sourceRows = Vue.ref(stockRows(62_032))
	const root = mountReport(sourceRows)
	await tick()
	assert.equal(dataRows(root).length, 200)
	assert.match(nodes(moreRow(root), "span")[0].text, /Showing 200 of 62,032 rows/)
	assert.equal(nodes(metric(root, "Stock rows"), "strong")[0].text, "62032")
	assert.equal(nodes(metric(root, "Balance quantity"), "strong")[0].text, "62032")
	assert.equal(nodes(metric(root, "In quantity"), "strong")[0].text, "124064")
	nodes(moreRow(root), "button")[0].props.onClick()
	await tick()
	assert.equal(dataRows(root).length, 400)
	sourceRows.value = stockRows(250)
	await tick()
	assert.equal(dataRows(root).length, 200, "a new result starts from the first step again")
	nodes(moreRow(root), "button")[0].props.onClick()
	await tick()
	assert.equal(dataRows(root).length, 250)
	assert.equal(moreRow(root), undefined)
})

test("Stock Balance mounts the next step when the end of the table scrolls into view", async () => {
	const observers = []
	globalThis.IntersectionObserver = class {
		constructor(callback) { this.callback = callback; this.targets = []; observers.push(this) }
		observe(target) { this.targets.push(target) }
		unobserve(target) { this.targets = this.targets.filter((item) => item !== target) }
		disconnect() { this.targets = [] }
	}
	try {
		const root = mountReport(Vue.ref(stockRows(500)))
		await tick()
		const [observer] = observers
		assert.ok(Vue.toRaw(observer.targets[0]) === moreRow(root))
		await observer.callback([{ isIntersecting: true }])
		await tick()
		assert.equal(dataRows(root).length, 400)
		assert.ok(Vue.toRaw(observer.targets[0]) === moreRow(root))
	} finally {
		delete globalThis.IntersectionObserver
	}
})

test("Stock Balance exports through the server so deferred rows are still exported", () => {
	const source = reportExport.deskExportSource("stock-balance", { from_date: "2026-09-22" }, columns)
	assert.ok(source.desk, "Desk-source exports rebuild every row on the server instead of reading the table DOM")
})

test("Stock Balance shows inward split dates as DD-MM-YYYY", async () => {
	const splitColumns = [...columns, { fieldname: "inward_split", label: "Inward Date Split", fieldtype: "Data" }]
	const root = mountReport(Vue.ref([{ item: "ITEM-1", bal_qty: 5, in_qty: 5, inward_split: "2026-10-23: 3\n2026-09-01: 2" }]), splitColumns)
	await tick()
	const cell = nodes(dataRows(root)[0], "span").find((node) => node.props.class === "multiline-cell")
	assert.equal(cell.text, "23-10-2026: 3\n01-09-2026: 2")
})
