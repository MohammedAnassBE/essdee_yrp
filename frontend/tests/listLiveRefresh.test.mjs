import assert from "node:assert/strict"
import test from "node:test"
import { effectScope, nextTick, ref } from "vue"

import { Vue, createTestRenderer, findNodes, loadComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as listColumns from "../src/components/common/listColumns.js"
import * as listItemFilters from "../src/components/common/listItemFilters.js"
import * as listStatusFilters from "../src/components/common/listStatusFilters.js"
import * as listNavigation from "../src/utils/listNavigation.js"
import * as prettyDate from "../src/utils/prettyDate.js"
import * as statusTone from "../src/utils/statusTone.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const previousDocument = globalThis.document
globalThis.document = { visibilityState: "visible", addEventListener() {}, removeEventListener() {} }
globalThis.window ??= { frappe: { boot: { site_name: "site.local" } }, location: { origin: "http://site.local", protocol: "http:", hostname: "site.local" } }

const realtime = await import("../src/api/realtime.js")
const live = await import("../src/components/common/listLiveRefresh.js")
const liveModule = live

const tick = async () => { await new Promise((resolve) => setImmediate(resolve)); await Vue.nextTick() }
const settle = async () => { await tick(); await tick(); await tick() }

function fakeSocket() {
	const handlers = new Map()
	return {
		connected: false, active: false, sent: [],
		io: { on() {}, reconnectionAttempts() {}, reconnectionDelayMax() {} },
		on(event, handler) { handlers.set(event, [...(handlers.get(event) || []), handler]) },
		off(event, handler) { handlers.set(event, (handlers.get(event) || []).filter((item) => item !== handler)) },
		connect() { this.active = true },
		emit(...args) { this.sent.push(args) },
		serverEmit(event, ...args) { for (const handler of handlers.get(event) || []) handler(...args) },
		open() { this.connected = true; this.serverEmit("connect") },
	}
}

test("changedRowNames flags new rows and rows with a new modified", () => {
	const before = [{ name: "A", modified: "1" }, { name: "B", modified: "1" }]
	const after = [{ name: "C", modified: "1" }, { name: "A", modified: "2" }, { name: "B", modified: "1" }]
	assert.deepEqual(live.changedRowNames(before, after), ["C", "A"])
})

test("mergeChangedRows updates in place and drops requested names that came back empty", () => {
	const rows = [{ name: "A", v: 1 }, { name: "B", v: 1 }, { name: "C", v: 1 }]
	const merged = live.mergeChangedRows(rows, [{ name: "B", v: 2 }], ["B", "C"])
	assert.deepEqual(merged, [{ name: "A", v: 1 }, { name: "B", v: 2 }])
	assert.equal(merged[0], rows[0], "untouched rows keep their identity")
})

test("keepSelection re-points selected rows at fresh objects and drops removed ones", () => {
	const fresh = [{ name: "A", v: 2 }]
	assert.deepEqual(live.keepSelection([{ name: "A", v: 1 }, { name: "Z" }], fresh), [fresh[0]])
	const empty = []
	assert.equal(live.keepSelection(empty, fresh), empty)
})

test("useRowHighlight marks rows for the highlight duration", (t) => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	const scope = effectScope()
	const { mark, isHighlighted } = scope.run(() => live.useRowHighlight(1600))
	mark(["A"])
	assert.equal(isHighlighted("A"), true)
	t.mock.timers.tick(1599)
	assert.equal(isHighlighted("A"), true)
	t.mock.timers.tick(1)
	assert.equal(isHighlighted("A"), false)
	scope.stop()
})

test("useListLiveRefresh batches list_update, holds while held and runs once the hold ends", async () => {
	const socket = fakeSocket()
	realtime.setSocketClientLoader(async () => ({ io: () => socket }))
	const held = ref(true)
	const calls = []
	let result = true
	const scope = effectScope()
	const liveList = scope.run(() => live.useListLiveRefresh({
		doctype: "ToDo",
		isHeld: () => held.value,
		refetch: async (change) => { calls.push(change); return result },
	}))
	await settle()
	socket.open()
	socket.serverEmit("list_update", { doctype: "ToDo", name: "A" })
	socket.serverEmit("list_update", { doctype: "Note", name: "X" })
	await new Promise((resolve) => setTimeout(resolve, 600))
	assert.equal(calls.length, 0, "held while rows are selected")
	held.value = false
	await nextTick()
	await settle()
	assert.deepEqual(calls, [{ names: ["A"], full: false }])

	result = false
	socket.serverEmit("list_update", { doctype: "ToDo", name: "B" })
	await new Promise((resolve) => setTimeout(resolve, 600))
	assert.deepEqual(calls.at(-1), { names: ["B"], full: false })
	result = true
	await liveList.request({ full: true })
	assert.deepEqual(calls.at(-1), { names: ["B"], full: true }, "a failed change is retried with the next one")

	held.value = true
	await nextTick()
	await liveList.request({ full: true })
	assert.equal(calls.length, 3, "an explicit refresh waits for the hold too")
	liveList.discardPending()
	held.value = false
	await nextTick()
	await settle()
	assert.equal(calls.length, 3, "a foreground load discards pending changes")
	scope.stop()
})

async function mountList(getList, { live = false } = {}) {
	const calls = { lists: [] }
	const mocks = {
		getMeta: async () => [{ name: "Entry", fields: [{ fieldname: "title", label: "Title", fieldtype: "Data", in_list_view: 1 }] }],
		getActiveWorkflow: async () => null,
		getUserListview: async () => ({ fields: [{ fieldname: "name" }, { fieldname: "title", fieldtype: "Data", in_list_view: 1 }], columns: null }),
		getItemFilterValues: async () => ({}),
		getList: async (doctype, options) => { calls.lists.push(options); return getList(options) },
		getCount: async () => 2,
		getCounts: async (doctype, sets) => sets.map(() => 0),
	}
	const stub = (name) => (props) => Vue.h(name, props)
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
	if (live) modules["./listLiveRefresh.js"] = liveModule
	const component = loadComponent("frontend/src/components/common/ListView.vue", modules)
	const shown = Vue.ref(true)
	const loaded = []
	const props = Vue.reactive({ doctype: "Entry", navigationEnabled: false, onLoaded: (event) => loaded.push(event) })
	const root = { type: "root", text: "", props: {}, children: [], parent: null, getRootNode() { return this }, addEventListener() {}, removeEventListener() {} }
	createTestRenderer().createApp({ render: () => (shown.value ? Vue.h(component, props) : null) }).mount(root)
	await settle()
	const node = (predicate) => findNodes(root, predicate)[0]
	const table = () => node((n) => n.type === "datatable")
	return {
		calls, table, loaded,
		select: async (index) => { table().props["onUpdate:selection"]([table().props.value[index]]); await settle() },
		clearSelection: async () => { table().props["onUpdate:selection"]([]); await settle() },
		unmount: async () => { shown.value = false; await settle() },
		refresh: async () => { node((n) => n.type === "button" && n.props.icon === "pi pi-refresh").props.onClick(); await settle() },
		hasNode: (className) => Boolean(node((n) => n.props?.class === className)),
		openFilters: async () => { node((n) => n.type === "button" && n.props.label === "Filters").props.onClick(); await settle() },
		closeFilters: async () => { node((n) => n.type === "./ListviewFilters.vue").props["onUpdate:visible"](false); await settle() },
	}
}

test("ListView refresh is silent: rows, selection and loaded range stay, changed rows highlight, errors keep rows", async () => {
	let answer = () => [{ name: "A", modified: "1" }, { name: "B", modified: "1" }]
	const list = await mountList(() => answer())
	assert.equal(list.table().props.value.length, 2)
	list.table().props["onUpdate:selection"]([list.table().props.value[1]])
	await settle()

	answer = () => [{ name: "C", modified: "1" }, { name: "A", modified: "2" }, { name: "B", modified: "1" }]
	await list.refresh()
	const table = list.table()
	assert.deepEqual(table.props.value.map((row) => row.name), ["C", "A", "B"])
	assert.equal(table.props.loading, false, "no table spinner")
	assert.deepEqual(table.props.selection.map((row) => row.name), ["B"], "selection kept")
	assert.equal(list.calls.lists.at(-1).start, 0)
	assert.equal(list.calls.lists.at(-1).pageLength, 50)
	const classes = Object.fromEntries(table.props.value.map((row) => [row.name, table.props["row-class"](row)]))
	assert.match(classes.C, /list-row--live-changed/)
	assert.match(classes.A, /list-row--live-changed/)
	assert.doesNotMatch(classes.B, /list-row--live-changed/)

	answer = () => { throw new Error("offline") }
	await list.refresh()
	assert.equal(list.table().props.value.length, 3, "rows kept on a failed refresh")
	assert.equal(list.hasNode("list-live-error"), true)
	assert.equal(list.hasNode("list-load-error"), false)
})

test.after(() => { globalThis.document = previousDocument })

function deferred() {
	let resolve
	const promise = new Promise((done) => { resolve = done })
	return { promise, resolve }
}

function liveHarness({ held = false } = {}) {
	const state = { held: ref(held), calls: [], gates: [], applied: [] }
	const scope = effectScope()
	const liveList = scope.run(() => live.useListLiveRefresh({
		doctype: "ToDo",
		isHeld: () => state.held.value,
		refetch: async (change, { canApply }) => {
			state.calls.push(change)
			const gate = deferred()
			state.gates.push(gate)
			await gate.promise
			if (!canApply()) return false
			state.applied.push(change)
			return true
		},
	}))
	return { ...state, liveList, scope }
}

test("a hold that starts while a refresh is in flight keeps its result unapplied and requeues it", async () => {
	realtime.setSocketClientLoader(async () => ({ io: () => fakeSocket() }))
	const harness = liveHarness()
	harness.liveList.request({ names: ["A"] })
	await settle()
	harness.held.value = true
	harness.gates[0].resolve()
	await settle()
	assert.deepEqual(harness.applied, [], "not applied while held")
	harness.held.value = false
	await nextTick()
	await settle()
	assert.deepEqual(harness.calls.at(-1), { names: ["A"], full: false }, "requeued change runs after the hold")
	harness.gates.at(-1).resolve()
	await settle()
	assert.deepEqual(harness.applied, [{ names: ["A"], full: false }])
	harness.scope.stop()
})

test("a coalesced rerun does not bypass a hold that began meanwhile", async () => {
	realtime.setSocketClientLoader(async () => ({ io: () => fakeSocket() }))
	const harness = liveHarness()
	harness.liveList.request({ names: ["A"] })
	await settle()
	harness.liveList.request({ names: ["B"] })
	harness.held.value = true
	await nextTick()
	harness.gates[0].resolve()
	await settle()
	assert.equal(harness.calls.length, 1, "rerun waits for the hold")
	harness.held.value = false
	await nextTick()
	await settle()
	assert.deepEqual(harness.calls.at(-1), { names: ["B", "A"], full: false })
	harness.gates.at(-1).resolve()
	await settle()
	harness.scope.stop()
})

test("disposal cancels the queued rerun and blocks applying the in-flight result", async () => {
	realtime.setSocketClientLoader(async () => ({ io: () => fakeSocket() }))
	const harness = liveHarness()
	harness.liveList.request({ names: ["A"] })
	await settle()
	harness.liveList.request({ names: ["B"] })
	harness.scope.stop()
	harness.gates[0].resolve()
	await settle()
	assert.equal(harness.calls.length, 1, "queued rerun cancelled")
	assert.deepEqual(harness.applied, [], "in-flight result dropped")
})

test("ListView keeps rows and selection when a selection starts mid-refresh, then applies after it clears", async () => {
	const socket = fakeSocket()
	realtime.setSocketClientLoader(async () => ({ io: () => socket }))
	let gate = null
	let answer = [{ name: "A", modified: "1" }, { name: "B", modified: "1" }]
	const list = await mountList(async () => { if (gate) await gate.promise; return answer }, { live: true })
	socket.open()
	await settle()
	gate = deferred()
	answer = [{ name: "C", modified: "1" }, { name: "B", modified: "1" }]
	socket.serverEmit("list_update", { doctype: "Entry", name: "C" })
	await new Promise((resolve) => setTimeout(resolve, 600))
	await list.select(0)
	gate.resolve()
	await settle()
	assert.deepEqual(list.table().props.value.map((row) => row.name), ["A", "B"], "rows not replaced while a row is selected")
	assert.deepEqual(list.table().props.selection.map((row) => row.name), ["A"], "selection untouched")
	gate = null
	await list.clearSelection()
	await settle()
	assert.deepEqual(list.table().props.value.map((row) => row.name), ["C", "B"], "held change applied after the selection clears")
})

test("ListView drops a background response that arrives after unmount", async () => {
	const socket = fakeSocket()
	realtime.setSocketClientLoader(async () => ({ io: () => socket }))
	let gate = null
	const list = await mountList(async () => { if (gate) await gate.promise; return [{ name: "A", modified: "1" }] }, { live: true })
	socket.open()
	await settle()
	const loadedBefore = list.loaded.length
	gate = deferred()
	list.refresh()
	await settle()
	await list.unmount()
	gate.resolve()
	await settle()
	assert.equal(list.loaded.length, loadedBefore, "no loaded event after unmount")
})

test("a manual refresh with rows selected waits with a hint and never drops a selected row deleted elsewhere", async () => {
	realtime.setSocketClientLoader(async () => ({ io: () => fakeSocket() }))
	let answer = [{ name: "A", modified: "1" }, { name: "B", modified: "1" }]
	const list = await mountList(async () => answer, { live: true })
	await list.select(1)
	answer = [{ name: "A", modified: "1" }]
	const fetchesBefore = list.calls.lists.length
	await list.refresh()
	assert.equal(list.calls.lists.length, fetchesBefore, "no fetch while rows are selected")
	assert.deepEqual(list.table().props.value.map((row) => row.name), ["A", "B"])
	assert.deepEqual(list.table().props.selection.map((row) => row.name), ["B"], "selection kept")
	assert.equal(list.hasNode("list-live-hint"), true, "tells the user the refresh is waiting")
	await list.clearSelection()
	await settle()
	assert.deepEqual(list.table().props.value.map((row) => row.name), ["A"], "refresh applies once the selection clears")
	assert.equal(list.hasNode("list-live-hint"), false)
})

test("a manual refresh waits while the filter dialog is open", async () => {
	realtime.setSocketClientLoader(async () => ({ io: () => fakeSocket() }))
	let answer = [{ name: "A", modified: "1" }]
	const list = await mountList(async () => answer, { live: true })
	await list.openFilters()
	answer = [{ name: "B", modified: "1" }, { name: "A", modified: "1" }]
	const fetchesBefore = list.calls.lists.length
	await list.refresh()
	assert.equal(list.calls.lists.length, fetchesBefore, "no fetch while the filter dialog is open")
	await list.closeFilters()
	await settle()
	assert.deepEqual(list.table().props.value.map((row) => row.name), ["B", "A"])
})
