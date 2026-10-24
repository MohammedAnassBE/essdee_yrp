import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as listColumns from "../src/components/common/listColumns.js"
import * as listNavigation from "../src/utils/listNavigation.js"
import * as statusTone from "../src/utils/statusTone.js"
import * as prettyDate from "../src/utils/prettyDate.js"
import * as listStatusFilters from "../src/components/common/listStatusFilters.js"
import * as listItemFilters from "../src/components/common/listItemFilters.js"
import {
	clearListScrollStates,
	listQueryFingerprint,
	listScrollStateKey,
	readListScrollState,
	saveListScrollState,
} from "../src/components/common/listScrollState.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const settle = async () => { await tick(); await tick(); await tick() }
const stub = name => (props) => Vue.h(name, props)
const fields = [{ fieldname: "status", label: "Status", fieldtype: "Select", options: "Draft\nOpen", in_list_view: 1 }]
const records = Array.from({ length: 120 }, (_, index) => ({ name: `ENT-${String(index + 1).padStart(3, "0")}`, status: "Open" }))

function memoryStorage() {
	const values = new Map()
	return { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, String(value)) }
}

async function mountList({ navigationEnabled = false, data = records } = {}) {
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: memoryStorage(), frappe: {} }
	const calls = { lists: [], totals: 0 }
	const mocks = {
		getMeta: async () => [{ name: "Entry", fields }],
		getActiveWorkflow: async () => null,
		getUserListview: async () => ({ fields: [{ fieldname: "name" }, ...fields], columns: null }),
		getItemFilterValues: async () => ({}),
		getList: async (doctype, options) => { calls.lists.push(options); return data.slice(options.start, options.start + options.pageLength) },
		getCount: async () => { calls.totals += 1; return data.length },
		getCounts: async (doctype, sets) => sets.map(() => data.length),
	}
	const modules = {
		"vue-router": { useRoute: () => ({ name: "entries", fullPath: "/entries" }) },
		"../../api/frappe.js": mocks,
		"./listColumns.js": listColumns,
		"../../utils/listNavigation.js": listNavigation,
		"../../utils/statusTone.js": statusTone,
		"../../utils/prettyDate.js": prettyDate,
		"./listStatusFilters.js": listStatusFilters,
		"./listItemFilters.js": listItemFilters,
	}
	for (const name of ["button", "column", "datatable", "dialog", "inputtext", "message", "select"]) modules[`primevue/${name}`] = stub(name)
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue", "./ListviewQuickFilters.vue"]) modules[path] = stub(path)
	modules["./asyncListParts.js"] = { FormField: stub("./FormField.vue"), UserListviewColumns: stub("./UserListviewColumns.vue"), ListviewFilters: stub("./ListviewFilters.vue") }
	const root = mountComponent(loadComponent("frontend/src/components/common/ListView.vue", modules), Vue.reactive({
		doctype: "Entry", navigationEnabled, statusField: "status", statusOptions: ["Draft", "Open"],
	}))
	await settle()
	const node = predicate => findNodes(root, predicate)[0]
	const text = predicate => { const found = node(predicate); return found ? [found, ...findNodes(found, () => true)].map(item => item.text || "").join("").trim() : "" }
	return {
		calls,
		cards: () => findNodes(root, n => n.type === "article").length,
		status: () => text(n => n.props?.class === "list-load-status"),
		loadMore: async () => { node(n => n.type === "button" && n.props.class === "list-load-more").props.onClick(); await settle() },
		hasLoadMore: () => Boolean(node(n => n.type === "button" && n.props.class === "list-load-more")),
		sort: async () => { node(n => n.type === "datatable").props.onSort({ sortField: "name", sortOrder: 1 }); await settle() },
		selectStatus: async value => { node(n => n.type === "button" && n.props.class?.includes?.("list-status-tab") && n.props["aria-pressed"] === false && n.children.some(child => (child.text || "").includes(value))).props.onClick(); await settle() },
		refresh: async () => { node(n => n.type === "button" && n.props.icon === "pi pi-refresh").props.onClick(); await settle() },
		openCard: async index => { findNodes(root, n => n.type === "button" && n.props.class === "mobile-list-record__open")[index].props.onClick({ stopPropagation() {} }); await settle() },
		restore: () => { globalThis.window = previousWindow },
	}
}

test("the first load fetches 50 rows and each load-more appends the next 50 without refetching the total", async () => {
	const list = await mountList()
	try {
		assert.deepEqual(list.calls.lists.map(({ start, pageLength }) => [start, pageLength]), [[0, 50]])
		assert.equal(list.cards(), 50)
		assert.match(list.status(), /Showing 50 of 120/)
		await list.loadMore()
		await list.loadMore()
		assert.deepEqual(list.calls.lists.map(({ start, pageLength }) => [start, pageLength]), [[0, 50], [50, 50], [100, 50]])
		assert.equal(list.cards(), 120)
		assert.equal(list.calls.totals, 1)
		assert.match(list.status(), /All 120 loaded/)
		assert.equal(list.hasLoadMore(), false)
	} finally { list.restore() }
})

test("an early end corrects a stale total so loading stops", async () => {
	const data = records.slice(0, 60)
	const list = await mountList({ data })
	try {
		data.splice(55)
		await list.loadMore()
		assert.equal(list.cards(), 55)
		assert.match(list.status(), /All 55 loaded/)
	} finally { list.restore() }
})

test("sort and status changes reset to the first 50 rows", async () => {
	const list = await mountList()
	try {
		await list.loadMore()
		assert.equal(list.cards(), 100)
		await list.sort()
		assert.deepEqual(list.calls.lists.at(-1).start, 0)
		assert.equal(list.calls.lists.at(-1).pageLength, 50)
		assert.equal(list.cards(), 50)
		await list.loadMore()
		await list.selectStatus("Draft")
		assert.equal(list.calls.lists.at(-1).pageLength, 50)
		assert.equal(list.cards(), 50)
	} finally { list.restore() }
})

test("refresh reloads the whole loaded range in one request", async () => {
	const list = await mountList()
	try {
		await list.loadMore()
		await list.refresh()
		assert.deepEqual([list.calls.lists.at(-1).start, list.calls.lists.at(-1).pageLength], [0, 100])
		assert.equal(list.cards(), 100)
	} finally { list.restore() }
})

test("opening a row saves the loaded count so a remounted list reloads the same rows", async () => {
	clearListScrollStates()
	const first = await mountList({ navigationEnabled: true })
	try {
		await first.loadMore()
		await first.openCard(80)
	} finally { first.restore() }
	const second = await mountList({ navigationEnabled: true })
	try {
		assert.deepEqual([second.calls.lists[0].start, second.calls.lists[0].pageLength], [0, 100])
		assert.equal(second.cards(), 100)
	} finally { second.restore() }
})

test("a saved position is only restored for the same query and survives in session storage", () => {
	clearListScrollStates()
	const storage = memoryStorage()
	const key = listScrollStateKey("entries", "Entry")
	const fingerprint = listQueryFingerprint({ status: "Open" })
	saveListScrollState(key, { fingerprint, loadedCount: 150, scrollTop: 2400 }, storage)
	clearListScrollStates()
	assert.deepEqual(readListScrollState(key, fingerprint, storage), { fingerprint, loadedCount: 150, scrollTop: 2400 })
	assert.equal(readListScrollState(key, listQueryFingerprint({ status: "Draft" }), storage), null)
	const blocked = { getItem() { throw new Error("blocked") }, setItem() { throw new Error("blocked") } }
	clearListScrollStates()
	assert.equal(readListScrollState(key, fingerprint, blocked), null)
	saveListScrollState(key, { fingerprint, loadedCount: 50, scrollTop: 0 }, blocked)
	assert.equal(readListScrollState(key, fingerprint, blocked).loadedCount, 50)
})
