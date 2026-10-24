import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as listColumns from "../src/components/common/listColumns.js"
import * as listNavigation from "../src/utils/listNavigation.js"
import * as statusTone from "../src/utils/statusTone.js"
import * as prettyDate from "../src/utils/prettyDate.js"
import * as listStatusFilters from "../src/components/common/listStatusFilters.js"
import * as listItemFilters from "../src/components/common/listItemFilters.js"
import { dateRangeFilters, dateRangePresets, dateRangeValue, hasDateRangeValue } from "../src/components/common/listDateRangeFilters.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const settle = async () => { await tick(); await tick(); await tick() }
const stub = name => (props, { slots }) => Vue.h(name, props, slots?.default?.())
const flatten = vnodes => vnodes.flatMap(vnode => vnode.type === Vue.Fragment ? flatten(vnode.children || []) : [vnode])
const fields = [
	{ fieldname: "status", label: "Status", fieldtype: "Select", options: "Draft\nOpen", in_list_view: 1 },
	{ fieldname: "posting_date", label: "Posting Date", fieldtype: "Date", in_list_view: 1, in_standard_filter: 1 },
]
const rows = [{ name: "ENT-1", status: "Open", posting_date: "2026-10-05", modified: "2026-10-05 10:00:00" }]

function dataTable(props, { slots }) {
	const columns = flatten(slots.default?.() || []).filter(column => column.children?.body)
	return Vue.h("table", {}, (props.value || []).map(row => Vue.h("tr", {}, columns.map(column =>
		Vue.h("td", { field: column.props?.field }, column.children.body({ data: row }))))))
}

async function mountList() {
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: {} }
	const calls = { lists: [], counts: [] }
	const api = {
		getMeta: async () => [{ name: "Entry", fields }],
		getActiveWorkflow: async () => null,
		getUserListview: async () => ({ fields: [{ fieldname: "name" }, ...fields], columns: null }),
		getItemFilterValues: async () => ({}),
		getList: async (doctype, args) => { calls.lists.push(args.filters); return rows },
		getCount: async () => rows.length,
		getCounts: async (doctype, sets) => { calls.counts.push(sets); return sets.map(() => 1) },
	}
	const modules = {
		"vue-router": { useRoute: () => ({ fullPath: "/entries" }) },
		"../../api/frappe.js": api,
		"./listColumns.js": listColumns,
		"../../utils/listNavigation.js": listNavigation,
		"../../utils/statusTone.js": statusTone,
		"../../utils/prettyDate.js": prettyDate,
		"./listStatusFilters.js": listStatusFilters,
		"./listItemFilters.js": listItemFilters,
	}
	for (const name of ["button", "column", "dialog", "inputtext", "message", "paginator", "select"]) modules[`primevue/${name}`] = stub(name)
	modules["primevue/datatable"] = dataTable
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue"]) modules[path] = stub(path)
	modules["./asyncListParts.js"] = { FormField: stub("./FormField.vue"), UserListviewColumns: stub("./UserListviewColumns.vue"), ListviewFilters: stub("advanced-filters") }
	modules["./ListviewQuickFilters.vue"] = stub("quick-filters")
	const root = mountComponent(loadComponent("frontend/src/components/common/ListView.vue", modules), Vue.reactive({
		doctype: "Entry", navigationEnabled: false, statusField: "status", statusOptions: ["Draft", "Open"],
	}))
	await settle()
	const quick = () => findNodes(root, node => node.type === "quick-filters")[0]
	return { calls, root, quick, restore: () => { globalThis.window = previousWindow } }
}

test("date range values build between, open-bound or no filters", () => {
	assert.deepEqual(dateRangeFilters("posting_date", ["2026-10-01", "2026-10-31"]), [["posting_date", "between", ["2026-10-01", "2026-10-31"]]])
	assert.deepEqual(dateRangeFilters("posting_date", ["2026-10-01", ""]), [["posting_date", ">=", "2026-10-01"]])
	assert.deepEqual(dateRangeFilters("posting_date", ["", "2026-10-31"]), [["posting_date", "<=", "2026-10-31"]])
	assert.deepEqual(dateRangeFilters("posting_date", "2026-10-05"), [["posting_date", "between", ["2026-10-05", "2026-10-05"]]])
	assert.deepEqual(dateRangeFilters("posting_date", ["", null]), [])
	assert.deepEqual(dateRangeValue("2026-10-05"), ["2026-10-05", "2026-10-05"])
	assert.equal(hasDateRangeValue([null, ""]), false)
	assert.equal(hasDateRangeValue(["2026-10-05", ""]), true)
})

test("presets cover today, Monday-start weeks and calendar months", () => {
	const presets = Object.fromEntries(dateRangePresets(new Date(2026, 9, 24)).map(preset => [preset.label, preset.value]))
	assert.deepEqual(presets, {
		Today: ["2026-10-24", "2026-10-24"],
		Yesterday: ["2026-10-23", "2026-10-23"],
		"This Week": ["2026-10-19", "2026-10-25"],
		"Last Week": ["2026-10-12", "2026-10-18"],
		"This Month": ["2026-10-01", "2026-10-31"],
		"Last Month": ["2026-09-01", "2026-09-30"],
	})
	assert.deepEqual(dateRangePresets(new Date(2026, 0, 4))[2].value, ["2025-12-29", "2026-01-04"])
})

test("a posting date range quick filter reaches get_list and every batched status count", async () => {
	const list = await mountList()
	try {
		const values = { posting_date: ["2026-10-01", "2026-10-31"] }
		list.quick().props.onChange({ values, field: fields[1] })
		await new Promise(resolve => setTimeout(resolve, 1100))
		await settle()
		const between = ["posting_date", "between", ["2026-10-01", "2026-10-31"]]
		assert.deepEqual(list.calls.lists.at(-1), [between])
		assert.deepEqual(list.calls.counts.at(-1), [[between], [between, ["status", "=", "Draft"]], [between, ["status", "=", "Open"]]])
	} finally { list.restore() }
})

test("clicking a posting date cell filters that one day as a range", async () => {
	const list = await mountList()
	try {
		const cell = findNodes(list.root, node => node.type === "td" && node.props.field === "posting_date")[0]
			.children.find(child => !["text", "comment"].includes(child.type))
		cell.props.onClick({ stopPropagation() {} })
		await settle()
		assert.deepEqual(list.quick().props.modelValue, { posting_date: ["2026-10-05", "2026-10-05"] })
		assert.deepEqual(list.calls.lists.at(-1), [["posting_date", "between", ["2026-10-05", "2026-10-05"]]])
	} finally { list.restore() }
})
