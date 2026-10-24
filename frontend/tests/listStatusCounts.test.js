import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as api from "../src/api/frappe.js"
import * as listColumns from "../src/components/common/listColumns.js"
import * as listNavigation from "../src/utils/listNavigation.js"
import * as statusTone from "../src/utils/statusTone.js"
import * as prettyDate from "../src/utils/prettyDate.js"
import * as listStatusFilters from "../src/components/common/listStatusFilters.js"
import * as listItemFilters from "../src/components/common/listItemFilters.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const settle = async () => { await tick(); await tick(); await tick() }
const stub = name => (props) => Vue.h(name, props)
const fields = [
	{ fieldname: "status", label: "Status", fieldtype: "Select", options: "Draft\nOpen\nClosed", in_list_view: 1 },
	{ fieldname: "items", label: "Items", fieldtype: "Table", options: "Entry Item" },
]

async function mountList({ counts = async (doctype, sets) => sets.map((_, index) => index + 1), totals = () => 100 } = {}) {
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: {} }
	const calls = { totals: [], batches: [] }
	const mocks = {
		getMeta: async () => [{ name: "Entry", fields }, { name: "Entry Item", fields: [{ fieldname: "item", fieldtype: "Data" }] }],
		getActiveWorkflow: async () => null,
		getUserListview: async () => ({ fields: [{ fieldname: "name" }, ...fields], columns: null }),
		getItemFilterValues: async () => ({}),
		getList: async (doctype, { start }) => start ? [{ name: "ENT-2", status: "Open" }] : [{ name: "ENT-1", status: "Open" }],
		getCount: async (doctype, filters, options) => { calls.totals.push({ filters, options }); return totals() },
		getCounts: async (doctype, sets, options) => { calls.batches.push({ doctype, sets, options }); return counts(doctype, sets) },
	}
	const modules = {
		"vue-router": { useRoute: () => ({ fullPath: "/entries" }) },
		"../../api/frappe.js": mocks,
		"./listColumns.js": listColumns,
		"../../utils/listNavigation.js": listNavigation,
		"../../utils/statusTone.js": statusTone,
		"../../utils/prettyDate.js": prettyDate,
		"./listStatusFilters.js": listStatusFilters,
		"./listItemFilters.js": listItemFilters,
	}
	for (const name of ["button", "column", "datatable", "dialog", "inputtext", "message", "paginator", "select"]) modules[`primevue/${name}`] = stub(name)
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue", "./ListviewQuickFilters.vue"]) modules[path] = stub(path)
	modules["./asyncListParts.js"] = { FormField: stub("./FormField.vue"), UserListviewColumns: stub("./UserListviewColumns.vue"), ListviewFilters: stub("./ListviewFilters.vue") }
	const root = mountComponent(loadComponent("frontend/src/components/common/ListView.vue", modules), Vue.reactive({
		doctype: "Entry", navigationEnabled: false, statusField: "status", statusOptions: ["Draft", "Open", "Closed"],
	}))
	await settle()
	const node = (predicate) => findNodes(root, predicate)[0]
	return {
		calls, root,
		tabCounts: () => findNodes(root, n => n.props?.class === "list-status-tab__count").map(n => (n.text || n.children.map(child => child.text).join("")).trim()),
		loadMore: async () => { node(n => n.type === "button" && n.props.class === "list-load-more").props.onClick(); await settle() },
		sort: async () => { node(n => n.type === "datatable").props.onSort({ sortField: "name", sortOrder: 1 }); await settle() },
		refresh: async () => { node(n => n.type === "button" && n.props.icon === "pi pi-refresh").props.onClick(); await settle() },
		restore: () => { globalThis.window = previousWindow },
	}
}

test("status counts come from one batch request in tab order", async () => {
	const list = await mountList()
	try {
		assert.equal(list.calls.batches.length, 1)
		const [batch] = list.calls.batches
		assert.equal(batch.doctype, "Entry")
		assert.deepEqual(batch.sets, [[], [["status", "=", "Draft"]], [["status", "=", "Open"]], [["status", "=", "Closed"]]])
		assert.deepEqual(batch.options, { distinct: false })
		assert.equal(list.calls.totals.length, 1)
		assert.deepEqual(list.tabCounts(), ["1", "2", "3", "4"])
	} finally { list.restore() }
})

test("appending a page reuses the total; sort and refresh refetch it so other users' writes show", async () => {
	let total = 100
	const list = await mountList({ totals: () => total })
	try {
		assert.equal(list.calls.totals.length, 1)
		total = 101
		await list.loadMore()
		assert.equal(list.calls.totals.length, 1)
		await list.sort()
		assert.equal(list.calls.totals.length, 2)
		assert.equal(list.calls.batches.length, 1)
		await list.refresh()
		assert.equal(list.calls.totals.length, 3)
		assert.equal(list.calls.batches.length, 2)
	} finally { list.restore() }
})

test("a failed batch falls back to the row total like a failed count did", async () => {
	const list = await mountList({ counts: async () => { throw new Error("denied") } })
	try {
		assert.equal(list.calls.batches.length, 1)
		assert.deepEqual(list.tabCounts(), ["100", "0", "0", "0"])
	} finally { list.restore() }
})

test("getCounts posts one request, sends distinct only when asked and rejects partial answers", async () => {
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { csrf_token: "token" }
	const requests = []
	let answer = [3, "4", null]
	globalThis.fetch = async (url, options) => {
		requests.push({ url, body: JSON.parse(options.body) })
		return { ok: true, status: 200, json: async () => ({ message: answer }) }
	}
	try {
		const sets = [[], [["status", "=", "Open"]], [["status", "=", "Closed"]]]
		assert.deepEqual(await api.getCounts("Entry", sets), [3, 4, 0])
		assert.equal(requests[0].url, "/api/method/essdee_yrp.api.list_counts.get_counts")
		assert.deepEqual(requests[0].body, { doctype: "Entry", filter_sets: sets })
		await api.getCounts("Entry", sets, { distinct: true })
		assert.equal(requests[1].body.distinct, true)
		answer = [1]
		api.invalidatePendingReads()
		await assert.rejects(api.getCounts("Entry", sets), /incomplete set of counts/)
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})

test("getCounts splits more than 100 filter sets into ordered requests", async () => {
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { csrf_token: "token" }
	const sizes = []
	globalThis.fetch = async (url, options) => {
		const { filter_sets: sets } = JSON.parse(options.body)
		sizes.push(sets.length)
		return { ok: true, status: 200, json: async () => ({ message: sets.map(([[, , value]]) => value) }) }
	}
	try {
		const sets = Array.from({ length: 205 }, (_, index) => [["idx", "=", index]])
		assert.deepEqual(await api.getCounts("Entry", sets), sets.map((_, index) => index))
		assert.deepEqual(sizes, [100, 100, 5])
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})
