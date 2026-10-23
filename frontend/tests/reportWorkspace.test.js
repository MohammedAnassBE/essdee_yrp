import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { chooseReport, readRememberedReport, rememberReport, reportGroups, stepReport } from "../src/components/reports/reportWorkspace.js"

const REPORTS = [
	{ value: "work-order", label: "Work Order", group: "Production" },
	{ value: "process-pending", label: "Process Pending", group: "Production" },
	{ value: "daily-production", label: "Daily Production", group: "Cutting", component: props => Vue.h("daily-report", props), props: { mode: "daily" } },
	{ value: "stock-balance", label: "Stock Balance", component: props => Vue.h("stock-report", props) },
]
const tick = async () => { await new Promise(done => setImmediate(done)); await Vue.nextTick() }
const nodes = (root, type) => findNodes(root, node => node.type === type)
const items = root => findNodes(root, node => node.type === "button" && String(node.props.class).includes("report-workspace__item"))
const label = node => findNodes(node, child => child.text?.trim()).map(child => child.text).join("")
const search = root => nodes(root, "inputtext")[0]

function mount(props, query = {}, slots) {
	const route = Vue.reactive({ path: "/planning/reports", query, hash: "#top" })
	const navigations = []
	const component = loadComponent(new URL("../src/components/reports/ReportWorkspace.vue", import.meta.url).pathname, {
		"primevue/inputtext": props => Vue.h("inputtext", props),
		"primevue/select": props => Vue.h("select", props),
		"vue-router": { useRoute: () => route, useRouter: () => ({ replace: to => { navigations.push(to); route.query = to.query } }) },
		"./reportWorkspace.js": { chooseReport, readRememberedReport, rememberReport, reportGroups, stepReport },
	})
	const root = mountComponent({ render: () => Vue.h(component, props, slots) }, {})
	return { root, route, navigations }
}

test("report search matches every word in label or group and keeps group order", () => {
	assert.deepEqual(reportGroups(REPORTS).map(group => [group.label, group.reports.map(report => report.value)]), [
		["Production", ["work-order", "process-pending"]], ["Cutting", ["daily-production"]], ["", ["stock-balance"]],
	])
	assert.deepEqual(reportGroups(REPORTS, "prod").flatMap(group => group.reports.map(report => report.value)), ["work-order", "process-pending", "daily-production"])
	assert.deepEqual(reportGroups(REPORTS, "  PENDING prod ").flatMap(group => group.reports.map(report => report.value)), ["process-pending"])
	assert.deepEqual(reportGroups(REPORTS, "nothing"), [])
})

test("report choice prefers the URL, then the remembered report, then the first", () => {
	assert.equal(chooseReport(REPORTS, "stock-balance", "work-order"), "stock-balance")
	assert.equal(chooseReport(REPORTS, "gone", "process-pending"), "process-pending")
	assert.equal(chooseReport(REPORTS, "", "gone"), "work-order")
	assert.equal(chooseReport([], "work-order", "work-order"), "")
	assert.deepEqual([stepReport(["a", "b"], "", 1), stepReport(["a", "b"], "", -1), stepReport(["a", "b"], "b", 1), stepReport(["a", "b"], "b", -1), stepReport([], "a", 1)], ["a", "b", "b", "a", ""])
})

test("remembered reports survive missing or throwing storage", () => {
	const original = Object.getOwnPropertyDescriptor(globalThis, "localStorage")
	try {
		Object.defineProperty(globalThis, "localStorage", { configurable: true, get: () => { throw new Error("blocked") } })
		assert.equal(readRememberedReport("cutting"), "")
		assert.doesNotThrow(() => rememberReport("cutting", "x"))
		const store = new Map()
		Object.defineProperty(globalThis, "localStorage", { configurable: true, value: { getItem: key => store.get(key) ?? null, setItem: (key, value) => store.set(key, value) } })
		rememberReport("cutting", "daily-production")
		assert.equal(readRememberedReport("cutting"), "daily-production")
		assert.equal(readRememberedReport("sewing"), "")
	} finally {
		if (original) Object.defineProperty(globalThis, "localStorage", original)
		else delete globalThis.localStorage
	}
})

test("the list shows grouped reports, highlights the selected one and keeps the choice in the URL", async () => {
	const { root, navigations } = mount({ reports: REPORTS, label: "Planning reports", queryKey: "report" }, { report: "daily-production", lot: "L1" })
	try {
		assert.deepEqual(items(root).map(label), ["Work Order", "Process Pending", "Daily Production", "Stock Balance"])
		assert.deepEqual(findNodes(root, node => node.type === "p" && node.props.class === "report-workspace__group").map(label), ["Production", "Cutting"])
		assert.deepEqual(items(root).map(item => item.props["aria-current"]), [undefined, undefined, "page", undefined])
		const report = nodes(root, "daily-report")[0]
		assert.equal(report.props.mode, "daily")
		items(root)[3].props.onClick()
		await tick()
		assert.deepEqual(navigations, [{ query: { report: "stock-balance", lot: "L1" }, hash: "#top" }])
		assert.equal(nodes(root, "stock-report").length, 1)
		assert.equal(nodes(root, "daily-report").length, 0)
		assert.equal(nodes(root, "select")[0].props.modelValue, "stock-balance")
	} finally { root.__vue_app__.unmount() }
})

test("typing filters the list, arrows move the highlight and Enter opens the report", async () => {
	const { root, navigations } = mount({ reports: REPORTS, queryKey: "tab" })
	try {
		search(root).props["onUpdate:modelValue"]("prod")
		await tick()
		assert.deepEqual(items(root).map(label), ["Work Order", "Process Pending", "Daily Production"])
		const key = name => { const event = { key: name, preventDefault() { event.prevented = true } }; search(root).props.onKeydown(event); return event }
		assert.equal(key("ArrowDown").prevented, true)
		await tick()
		assert.match(items(root)[1].props.class, /is-highlighted/)
		key("ArrowDown"); key("ArrowDown"); key("Enter")
		await tick()
		assert.deepEqual(navigations.at(-1).query, { tab: "daily-production" })
		search(root).props["onUpdate:modelValue"]("zzz")
		await tick()
		assert.equal(items(root).length, 0)
		assert.ok(findNodes(root, node => node.text?.includes("No report matches")).length)
		key("Enter")
		assert.equal(navigations.length, 1)
		key("Escape")
		await tick()
		assert.equal(items(root).length, 4)
	} finally { root.__vue_app__.unmount() }
})

test("a single report renders full width without the picker and slots receive the report", () => {
	const single = mount({ reports: [REPORTS[0]] })
	try {
		assert.equal(nodes(single.root, "nav").length, 0)
		assert.equal(nodes(single.root, "select").length, 0)
	} finally { single.root.__vue_app__.unmount() }
	const slotted = mount({ reports: REPORTS }, { report: "process-pending" }, { default: ({ report }) => Vue.h("slot-report", { value: report.value }) })
	try {
		assert.equal(nodes(slotted.root, "slot-report")[0].props.value, "process-pending")
	} finally { slotted.root.__vue_app__.unmount() }
})
