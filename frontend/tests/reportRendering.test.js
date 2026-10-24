import assert from "node:assert/strict"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { reconcileReportLayout, reportCellValue, hydrateLinkedValueBatches } from "../src/composables/reportColumns.js"
import * as incrementalRows from "../src/composables/useIncrementalRows.js"
import * as inlineFilters from "../src/composables/useInlineFilters.js"
import { useCopyFeedback } from "../src/composables/useCopyFeedback.js"
import { useReportColumns } from "../src/composables/useReportColumns.js"
import { useWebReport } from "../src/composables/useWebReport.js"
import { formatDisplayByFieldtype } from "../src/utils/dateFormat.js"

const tick = async () => { await new Promise(done => setImmediate(done)); await Vue.nextTick() }
const nodes = (root, type) => findNodes(root, node => node.type === type)

function withBrowser(globals, run) {
	const previous = Object.fromEntries(Object.keys(globals).map(key => [key, globalThis[key]]))
	Object.assign(globalThis, globals)
	return Promise.resolve().then(run).finally(() => Object.assign(globalThis, previous))
}

test("useWebReport keeps report rows as plain objects replaced as a whole", async () => {
	const envelope = { mode: "sync", columns: [{ fieldname: "item", label: "Item" }, { fieldname: "qty", label: "Qty", fieldtype: "Float" }], result: [{ item: "Tee", qty: 2 }, ["Total", 2]] }
	const storage = { getItem: () => null, setItem() {}, removeItem() {} }
	await withBrowser({
		window: { csrf_token: "", sessionStorage: storage, setTimeout, clearTimeout },
		document: { addEventListener() {}, removeEventListener() {}, visibilityState: "visible" },
		fetch: async () => ({ status: 200, ok: true, json: async () => ({ message: envelope }) }),
	}, async () => {
		let report
		const root = mountComponent({ setup() { report = useWebReport({ reportKey: "planning-work-order" }); return () => null } })
		try {
			await report.generate({ lot: "L-1" })
			assert.equal(report.state.value, "ready")
			assert.deepEqual(report.sourceRows.value, [{ item: "Tee", qty: 2 }, { is_total_row: true, item: "Total", qty: 2 }])
			assert.equal(Vue.isReactive(report.sourceRows.value), false)
			assert.equal(Vue.isReactive(report.sourceRows.value[0]), false)
			assert.equal(Vue.isReactive(report.payload.value), false)
			assert.equal(report.sourceColumns.value, envelope.columns)
			const seen = []
			Vue.watch(report.sourceRows, rows => seen.push(rows.length))
			report.clear()
			await Vue.nextTick()
			assert.deepEqual(seen, [0], "replacing the array still notifies watchers")
		} finally { root.__vue_app__.unmount() }
	})
})

test("useReportColumns returns the source rows untouched unless a linked column is shown", async () => {
	const sourceColumns = Vue.ref([{ fieldname: "item", label: "Item", fieldtype: "Link", options: "Item" }, { fieldname: "qty", label: "Qty", fieldtype: "Float" }])
	const sourceRows = Vue.shallowRef([{ item: "Tee", qty: 2 }, { is_total_row: true, qty: 2 }])
	await withBrowser({ window: { csrf_token: "" }, fetch: () => new Promise(() => {}) }, async () => {
		let layout
		const root = mountComponent({ setup() { layout = useReportColumns({ reportKey: "planning-work-order", sourceColumns, sourceRows }); return () => null } })
		try {
			assert.equal(layout.hasLinkedColumns.value, false)
			assert.equal(layout.rows.value, sourceRows.value)
			const linked = { key: "linked:item:item_group", kind: "linked", source_column: "item", target_field: "item_group", visible: true }
			layout.applyLayout([...reconcileReportLayout(sourceColumns.value, null), linked])
			await tick()
			assert.equal(layout.hasLinkedColumns.value, true)
			assert.notEqual(layout.rows.value, sourceRows.value)
			assert.deepEqual(layout.rows.value[0], { item: "Tee", qty: 2, __linked: { } })
			assert.equal(layout.rows.value[1], sourceRows.value[1], "the total row is never copied")
			assert.equal(reportCellValue(layout.rows.value[0], layout.displayColumns.value.at(-1)), "")
		} finally { root.__vue_app__.unmount() }
	})
})

test("linked value batches run three at a time and merge in batch order", async () => {
	const batches = Array.from({ length: 7 }, (_, index) => [{ source_column: "item", names: [`I-${index}`] }])
	const pending = []
	let inFlight = 0, peak = 0
	const fetchBatch = requests => new Promise(done => {
		inFlight += 1
		peak = Math.max(peak, inFlight)
		pending.push(() => { inFlight -= 1; done({ item: { [requests[0].names[0]]: { n: requests[0].names[0] }, shared: { n: requests[0].names[0] } } }) })
	})
	let settled = false
	const result = hydrateLinkedValueBatches(batches, fetchBatch, () => true).finally(() => { settled = true })
	while (!settled) {
		await tick()
		pending.splice(0).reverse().forEach(finish => finish())
	}
	const values = await result
	assert.equal(peak, 3)
	assert.deepEqual(Object.keys(values.item), ["I-0", "shared", "I-1", "I-2", "I-3", "I-4", "I-5", "I-6"])
	assert.deepEqual(values.item.shared, { n: "I-6" }, "a later batch wins exactly as the sequential merge did")
})

test("a stale linked value hydration starts no new batch and returns nothing", async () => {
	let current = true, calls = 0
	const fetchBatch = () => { calls += 1; return new Promise(done => setImmediate(() => { current = false; done({ item: { A: {} } }) })) }
	const result = await hydrateLinkedValueBatches(Array.from({ length: 9 }, () => [{}]), fetchBatch, () => current)
	assert.equal(result, null)
	assert.equal(calls, 3, "only the batches already started finish")
	await assert.rejects(hydrateLinkedValueBatches([[{}], [{}]], async () => { throw new Error("denied") }, () => true), /denied/)
	let started = 0
	const failFirst = index => () => { started += 1; return new Promise((done, fail) => setImmediate(() => index === 0 ? fail(new Error("denied")) : done({}))) }
	await assert.rejects(hydrateLinkedValueBatches(Array.from({ length: 9 }, (_, index) => index), index => failFirst(index)(), () => true), /denied/)
	await new Promise(done => setTimeout(done, 20))
	assert.equal(started, 3, "no batch starts after the first failure")
})

function mountShell(props, copy = async () => {}) {
	const opened = []
	const ExportStub = Vue.defineComponent({
		props: { prepareRows: Function },
		setup(stubProps, { expose }) {
			expose({ open: async () => { opened.push(await stubProps.prepareRows()) }, canExport: Vue.ref(true) })
			return () => null
		},
	})
	const shell = loadComponent(resolve(import.meta.dirname, "../src/components/reports/ReportShell.vue"), {
		"primevue/button": props => Vue.h("button", props), "primevue/message": () => null, "primevue/skeleton": () => null,
		"./copyElementAsImage.js": { copyElementAsImage: copy, copyPendingImage: () => false },
		"../../composables/useCopyFeedback.js": { useCopyFeedback: options => useCopyFeedback({ ...options, toast: { add() {} } }) },
		"../../composables/useIncrementalRows.js": incrementalRows,
		"./ReportActions.vue": props => Vue.h("menu", props), "./ReportExportButton.vue": ExportStub,
		"./reportExport.js": { renderedReportRows: () => [] },
		"../navigation/InlinePageNavigation.vue": () => null,
		"../navigation/pageNavigationContext.js": { usePageNavigation: () => null },
	})
	let table
	const Table = { setup() { table = incrementalRows.useIncrementalRows(Vue.ref(Array.from({ length: 450 }, (_, index) => index))); return () => Vue.h("table", table.renderedRows.value.length) } }
	const root = mountComponent({ render: () => Vue.h(shell, { title: "Work Order", generated: true, hasResults: true, ...props }, { default: () => Vue.h(Table) }) })
	return { root, opened, table: () => table }
}
const exportItem = root => nodes(root, "menu")[0].props.items.find(item => item?.label === "Export")

test("Copy Report mounts every row of the shell's incremental tables before beforeCopy and the capture", async () => {
	const calls = []
	const { root, table } = mountShell({ copyable: true, beforeCopy: async () => { calls.push(`prepare:${table().renderedRows.value.length}`) } }, async () => calls.push(`copy:${table().renderedRows.value.length}`))
	try {
		await tick()
		assert.equal(table().renderedRows.value.length, 200)
		nodes(root, "button").find(button => button.props.label === "Copy Report").props.onClick()
		await tick()
		assert.deepEqual(calls, ["prepare:450", "copy:450"])
		assert.equal(table().renderedRows.value.length, 200, "the table steps back after the capture")
	} finally { root.__vue_app__.unmount() }
})

test("a rendered export mounts every row first, while a Desk export reads nothing from the table", async () => {
	for (const [exportSource, expected] of [[{ reportKey: "planning-work-order" }, 450], [{ reportKey: "stock-balance", desk: { filters: {} } }, 200]]) {
		const before = []
		const { root, opened, table } = mountShell({ exportSource, beforeExport: async () => { before.push(table().renderedRows.value.length); return () => before.push("restored") } })
		try {
			await tick()
			exportItem(root).command()
			await tick()
			assert.deepEqual([opened.length, table().renderedRows.value.length], [1, expected])
			assert.deepEqual(before, exportSource.desk ? [] : [450])
			opened[0]?.()
			await tick()
			assert.equal(table().renderedRows.value.length, 200)
			assert.deepEqual(before, exportSource.desk ? [] : [450, "restored"])
		} finally { root.__vue_app__.unmount() }
	}
})

function mountRunStatus(props) {
	const timers = []
	const window = { setTimeout: (callback, delay) => { timers.push({ callback, delay }); return timers.length }, clearTimeout: id => { if (timers[id - 1]) timers[id - 1].cleared = true } }
	globalThis.window = window
	const status = loadComponent(resolve(import.meta.dirname, "../src/components/reports/ReportRunStatus.vue"), { "primevue/button": () => null, "primevue/progressbar": () => null })
	const state = Vue.reactive(props)
	const root = mountComponent({ render: () => Vue.h(status, state) })
	return { root, state, live: () => timers.filter(timer => !timer.cleared) }
}

test("ReportRunStatus ticks every second only while a job runs and otherwise only when its label changes", async () => {
	const previousWindow = globalThis.window
	try {
		const idle = mountRunStatus({ state: "ready", showGenerated: false })
		assert.deepEqual(idle.live(), [], "a sync result keeps no timer")
		idle.state.state = "running"
		idle.state.trackingStartedAt = Date.now()
		await tick()
		assert.deepEqual(idle.live().map(timer => timer.delay), [1_000])
		idle.live()[0].callback()
		assert.deepEqual(idle.live().map(timer => timer.delay), [1_000])
		idle.root.__vue_app__.unmount()
		assert.deepEqual(idle.live(), [])

		const generatedAt = new Date(Date.now() - 90_000)
		const generated = mountRunStatus({ state: "ready", showGenerated: true, generatedAt })
		const [timer] = generated.live()
		assert.ok(timer.delay > 29_000 && timer.delay <= 30_000, `wakes at the 2 min label, not every second (${timer.delay})`)
		assert.match(findNodes(generated.root, node => node.type === "text" && /Generated/.test(node.text)).map(node => node.text).join(""), /Generated 1 min ago/)
		generated.state.showGenerated = false
		await tick()
		assert.deepEqual(generated.live(), [])
		generated.root.__vue_app__.unmount()
	} finally { globalThis.window = previousWindow }
})

test("Cut Bundle Balance mounts rows in steps and hands ReportShell a full render for its rendered export", async () => {
	const columns = [{ fieldname: "lot", label: "Lot", fieldtype: "Data" }, { fieldname: "qty", label: "Qty", fieldtype: "Float" }]
	const sourceRows = Vue.shallowRef(Array.from({ length: 450 }, (_, index) => ({ lot: `L-${index}`, qty: 1 })))
	let shellProps
	const report = loadComponent(resolve(import.meta.dirname, "../src/departments/cut-panel-store/CutBundleBalanceReport.vue"), {
		"primevue/button": props => Vue.h("button", props),
		"../../composables/useIncrementalRows.js": incrementalRows, "../../composables/useInlineFilters.js": inlineFilters,
		"../../composables/useWebReport.js": { useWebReport: () => ({ state: Vue.ref("ready"), sourceColumns: Vue.ref(columns), sourceRows, job: Vue.ref(null), activeFilters: Vue.ref(null), generate: async () => {}, filtersChanged() {}, clear() {} }) },
		"../../composables/useReportColumns.js": { useReportColumns: () => {
			const displayColumns = Vue.computed(() => reconcileReportLayout(columns, null))
			return { columns: displayColumns, displayColumns, rows: sourceRows, linkSources: Vue.ref({}), fieldsBySource: Vue.ref({}), loadLayout() {}, cellValue: reportCellValue, cellAlign: () => "" }
		} },
		"../../components/common/LinkField.vue": () => null, "../../components/reports/ReportColumnPicker.vue": () => null,
		"../../components/reports/ReportFilterRow.vue": () => null, "../../components/reports/ReportRunStatus.vue": () => null,
		"../../components/reports/reportFilterState.js": { cutBundleFormFilters: request => request },
		"../../components/reports/ReportShell.vue": (props, { slots }) => { shellProps = props; return Vue.h("report-shell", props, [slots.metrics?.(), slots.default?.()]) },
		"../../components/reports/reportUtils.js": { number: value => String(value) },
		"../../utils/dateFormat.js": { formatDisplayByFieldtype },
	})
	const root = mountComponent(report)
	const dataRows = () => nodes(nodes(root, "tbody")[0], "tr").filter(row => row.props.class !== "cut-bundle-balance__more")
	try {
		await tick()
		assert.equal(dataRows().length, 200)
		const more = nodes(root, "tr").find(row => row.props.class === "cut-bundle-balance__more")
		assert.ok("data-export-ignore" in more.props)
		assert.ok(findNodes(root, node => node.text === "450").length, "metrics count every row")
		;(shellProps.beforeExport || shellProps["before-export"])()
		await tick()
		assert.equal(dataRows().length, 450)
	} finally { root.__vue_app__.unmount() }
})

test("the export dialog mounts rows again before Download and steps back when it closes", async () => {
	const calls = [], events = []
	const passthrough = name => (props, { slots }) => Vue.h(name, props, [slots.default?.(), slots.footer?.()])
	const button = loadComponent(resolve(import.meta.dirname, "../src/components/reports/ReportExportButton.vue"), {
		"primevue/button": props => Vue.h("export-button", props),
		"primevue/checkbox": () => null, "primevue/inputtext": () => null, "primevue/message": () => null,
		"primevue/select": () => null, "primevue/textarea": () => null, "primevue/dialog": passthrough("export-dialog"),
		"../../api/reportExport.js": { getExportPermission: async () => true, exportWebReport: async () => {}, exportReportRows: async args => calls.push(args.rows.length) },
		"./reportExport.js": await import("../src/components/reports/reportExport.js"),
	})
	// Mirrors useIncrementalRows.renderAllRows: a restore made before a row reset does nothing.
	let mounted = 200, resets = 0
	const prepareRows = async () => {
		events.push("prepare")
		const previous = mounted, generation = resets
		mounted = 450
		return () => { if (generation === resets) mounted = previous }
	}
	const getRows = () => Array.from({ length: mounted }, (_, index) => [index])
	const root = mountComponent(button, { title: "Work Order", source: { reportKey: "planning-work-order" }, getRows, prepareRows })
	try {
		await tick()
		const byLabel = label => findNodes(root, node => node.type === "export-button" && node.props.label === label)[0]
		const exportAndDownload = async ({ reset }) => {
			byLabel("Export").props.onClick()
			await tick()
			if (reset) { resets += 1; mounted = 200 } // linked values or an inline filter replaced the rows
			byLabel("Download").props.onClick()
			await tick()
		}
		await exportAndDownload({ reset: true })
		assert.deepEqual(calls, [450])
		assert.deepEqual(events, ["prepare", "prepare"], "Download prepares again")
		assert.equal(mounted, 200, "closing after a reset steps back to the reset's limit")
		await exportAndDownload({ reset: false })
		assert.deepEqual(calls, [450, 450])
		assert.equal(mounted, 200, "closing without a reset steps back to the limit before Export")
	} finally { root.__vue_app__.unmount() }
})
