import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import * as reportConfig from "../src/components/reports/deskReportConfig.js"
import * as reportExport from "../src/components/reports/reportExport.js"
import { cellAlign, reconcileReportLayout, reportCellValue } from "../src/composables/reportColumns.js"
import * as incrementalRows from "../src/composables/useIncrementalRows.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

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
		"./deskReportConfig.js": reportConfig, "../../composables/useIncrementalRows.js": incrementalRows, "./reportExport.js": reportExport,
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
