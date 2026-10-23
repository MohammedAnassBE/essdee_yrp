import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { useCopyFeedback } from "../src/composables/useCopyFeedback.js"

globalThis.window ??= globalThis
const tick = async () => { await new Promise(done => setImmediate(done)); await Vue.nextTick() }
const nodes = (root, type) => findNodes(root, node => node.type === type)

function mountShell(props, { copy = () => new Promise(() => {}), toast = { add() {} } } = {}) {
	const opened = [], emitted = []
	const ExportStub = Vue.defineComponent({
		setup(_props, { expose }) {
			expose({ open: () => opened.push(true), canExport: Vue.ref(true) })
			return () => Vue.h("export-dialog")
		},
	})
	const component = loadComponent(new URL("../src/components/reports/ReportShell.vue", import.meta.url).pathname, {
		"primevue/button": props => Vue.h("button", props),
		"primevue/menu": props => Vue.h("menu", props),
		"primevue/message": () => null,
		"primevue/skeleton": () => null,
		"./copyElementAsImage.js": { copyElementAsImage: copy, copyPendingImage: () => false },
		"../../composables/useCopyFeedback.js": { useCopyFeedback: options => useCopyFeedback({ ...options, toast }) },
		"./ReportExportButton.vue": ExportStub,
		"./reportExport.js": { renderedReportRows: () => [] },
		"../navigation/InlinePageNavigation.vue": () => null,
		"../navigation/pageNavigationContext.js": { usePageNavigation: () => null },
	})
	const root = mountComponent(component, { title: "DPR", onReset: () => emitted.push("reset"), ...props })
	return { root, opened, emitted }
}
const buttons = root => nodes(root, "button")
const menuItems = root => nodes(root, "menu")[0]?.props.model || []

test("reports show only Generate and Copy, with the rest in the more-actions menu", async () => {
	const pick = []
	const { root, opened, emitted } = mountShell({
		copyable: true, generated: true, hasResults: true, exportSource: { doctype: "SD YRP Sewing Plan" },
		actions: [
			{ label: "Pick Columns", icon: "pi pi-table", disabled: false, command: () => pick.push(true) },
			{ label: "Download", icon: "pi pi-download", visible: false, command() {} },
		],
	})
	try {
		await tick()
		assert.deepEqual(buttons(root).map(button => button.props.label ?? button.props["aria-label"]), ["Generate", "Copy Report", "More report actions"])
		const trigger = buttons(root)[2]
		assert.equal(trigger.props["aria-haspopup"], "menu")
		assert.equal(trigger.props["aria-controls"], nodes(root, "menu")[0].props.id)
		assert.deepEqual(menuItems(root).map(item => [item.label, Boolean(item.disabled)]), [["Reset", false], ["Export", false], ["Pick Columns", false]])
		for (const item of menuItems(root)) item.command()
		assert.deepEqual([emitted, opened.length, pick.length], [["reset"], 1, 1])
	} finally { root.__vue_app__.unmount() }
})

test("menu items keep their disabled state and Copy keeps its progress state", async () => {
	const { root } = mountShell({ copyable: true, generated: false, loading: true, exportSource: { doctype: "X" } })
	try {
		await tick()
		assert.deepEqual(menuItems(root).map(item => [item.label, item.disabled]), [["Reset", true], ["Export", true]])
	} finally { root.__vue_app__.unmount() }
	const ready = mountShell({ copyable: true, generated: true, hasResults: true })
	try {
		await tick()
		buttons(ready.root)[1].props.onClick()
		await tick()
		const copy = buttons(ready.root)[1]
		assert.deepEqual([copy.props.label, copy.props.loading], ["Copying", true])
		assert.deepEqual(menuItems(ready.root).map(item => item.label), ["Reset"])
	} finally { ready.root.__vue_app__.unmount() }
})

test("Copy shows a check and Copied with a toast after success, and an error toast on failure", async () => {
	for (const failure of [null, new Error("The browser blocked the clipboard.")]) {
		const toasts = []
		const { root } = mountShell({ copyable: true, generated: true, hasResults: true }, {
			copy: async () => { if (failure) throw failure },
			toast: { add: message => toasts.push(message) },
		})
		try {
			await tick()
			buttons(root)[1].props.onClick()
			await tick()
			const copy = buttons(root)[1]
			const expected = failure ? ["Copy Report", "pi pi-copy", "error"] : ["Copied", "pi pi-check", "success"]
			assert.deepEqual([copy.props.label, copy.props.icon, toasts[0]?.severity], expected)
			if (failure) assert.equal(toasts[0].detail, failure.message)
		} finally { root.__vue_app__.unmount() }
	}
})

test("optional report filters share the report grid and fold behind an accessible toggle", async () => {
	const component = loadComponent(new URL("../src/components/reports/ReportMoreFilters.vue", import.meta.url).pathname, {})
	const root = mountComponent({ render: () => Vue.h(component, { activeCount: 2 }, { default: () => Vue.h("lot-field") }) }, {})
	try {
		const toggle = nodes(root, "button")[0]
		const panel = findNodes(root, node => node.props.class === "report-more-filters__fields")[0]
		assert.equal(toggle.props["aria-controls"], panel.props.id)
		assert.equal(nodes(panel, "lot-field").length, 1)
		assert.ok(findNodes(toggle, node => node.text === "2 active").length)
		const expanded = toggle.props["aria-expanded"]
		toggle.props.onClick()
		await tick()
		assert.equal(nodes(root, "button")[0].props["aria-expanded"], !expanded)
	} finally { root.__vue_app__.unmount() }
})
