import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as api from "../src/api/frappe.js"
import * as listColumns from "../src/components/common/listColumns.js"
import * as listItemFilters from "../src/components/common/listItemFilters.js"
import * as listStatusFilters from "../src/components/common/listStatusFilters.js"
import * as listNavigation from "../src/utils/listNavigation.js"
import * as prettyDate from "../src/utils/prettyDate.js"
import * as statusTone from "../src/utils/statusTone.js"
import * as orderedDraft from "../src/components/common/orderedDraft.js"
import * as documentValues from "../src/utils/documentValues.js"
import * as pdViews from "../src/departments/pd/pdViews.js"
import * as purchaseViews from "../src/departments/purchase/purchaseViews.js"
import * as planningViews from "../src/departments/planning/planningViews.js"
import * as merchViews from "../src/departments/merch/merchViews.js"
import * as accountsViews from "../src/departments/accounts/accountsViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdRoutes.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseRoutes.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningRoutes.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchRoutes.js"
import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsRoutes.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const tick = async () => { await new Promise((resolve) => setImmediate(resolve)); await Vue.nextTick() }
const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
const dialogStub = (props, { slots }) => Vue.h("dialog", props, [slots.default?.(), slots.footer?.()])

test("the router reads route names from small modules, not the department view helpers", () => {
	const router = source("../src/router/index.js")
	assert.doesNotMatch(router, /Views\.js"/)
	for (const name of ["pd/pdRoutes", "purchase/purchaseRoutes", "planning/planningRoutes", "merch/merchRoutes", "accounts/accountsRoutes"]) {
		assert.match(router, new RegExp(`from "\\.\\./departments/${name}\\.js"`))
	}
	assert.equal(pdViews.PD_ROUTES, PD_ROUTES)
	assert.equal(purchaseViews.PURCHASE_ROUTES, PURCHASE_ROUTES)
	assert.equal(planningViews.PLANNING_ROUTES, PLANNING_ROUTES)
	assert.equal(merchViews.MERCH_ROUTES, MERCH_ROUTES)
	assert.equal(accountsViews.ACCOUNTS_ROUTES, ACCOUNTS_ROUTES)
	for (const file of ["pd/pdRoutes", "purchase/purchaseRoutes", "planning/planningRoutes", "merch/merchRoutes", "accounts/accountsRoutes"]) {
		assert.doesNotMatch(source(`../src/departments/${file}.js`), /^import /m)
	}
})

test("account dialogs and socket.io are not static imports", () => {
	const menu = source("../src/components/navigation/AccountMenu.vue")
	assert.doesNotMatch(menu, /^import .*(DocumentConfirmationDialog|ChangePasswordDialog|primevue\/message)/m)
	assert.match(menu, /<DocumentConfirmationDialog\s+v-if="confirmationLoaded"/)
	assert.match(menu, /<ChangePasswordDialog v-if="passwordDialogLoaded"/)
	assert.doesNotMatch(source("../src/api/realtime.js"), /^import .*socket\.io-client/m)
	assert.match(source("../src/components/documents/DocumentConfirmationDialog.vue"), /explicitReturnFocusSelector = props\.returnFocusSelector\n\}, \{ immediate: true \}\)/)
})

test("list filter, column and bulk-edit editors load on demand", () => {
	const list = source("../src/components/common/ListView.vue")
	assert.doesNotMatch(list, /^import .*(FormField|ListviewFilters|UserListviewColumns)\.vue/m)
	assert.match(list, /import \{ FormField, ListviewFilters, loadFormField, UserListviewColumns \} from "\.\/asyncListParts\.js"/)
	const quick = source("../src/components/common/ListviewQuickFilters.vue")
	assert.doesNotMatch(quick, /^import .*(DateField|DateTimeField|TimeField)\.vue/m)
	const parts = source("../src/components/common/asyncListParts.js")
	assert.match(parts, /export const loadFormField = \(\) => import\("\.\/FormField\.vue"\)\nexport const FormField = defineAsyncComponent\(loadFormField\)/)
	for (const name of ["ListviewFilters", "UserListviewColumns", "DateField", "DateTimeField", "TimeField"]) {
		assert.match(parts, new RegExp(`export const ${name} = defineAsyncComponent\\(\\(\\) => import\\("\\./${name}\\.vue"\\)\\)`))
	}
})

let realtimeCopies = 0

/** A fresh copy of the realtime module (own socket state) using `loadClient` for socket.io-client. */
async function realtimeModule(loadClient) {
	globalThis.window = {
		frappe: { boot: { site_name: "site.local" } },
		location: { origin: "http://site.local", protocol: "http:", hostname: "site.local" },
	}
	const realtime = await import(`../src/api/realtime.js?copy=${++realtimeCopies}`)
	realtime.setSocketClientLoader(loadClient)
	return realtime
}

function fakeSocket() {
	const handlers = new Map()
	return {
		connected: false, active: false, connects: 0, url: "",
		on(event, handler) { handlers.set(event, [...(handlers.get(event) || []), handler]) },
		off(event, handler) { handlers.set(event, (handlers.get(event) || []).filter((item) => item !== handler)) },
		connect() { this.connects += 1; this.active = true },
		emit(event, payload) { for (const handler of handlers.get(event) || []) handler(payload) },
		count(event) { return (handlers.get(event) || []).length },
	}
}

test("realtime loads the client once, subscribes in order and connects once", async () => {
	const socket = fakeSocket()
	let loads = 0
	const realtime = await realtimeModule(async () => { loads += 1; return { io: (url, options) => { socket.url = url; socket.options = options; return socket } } })
	const seen = []
	const offDone = realtime.onRealtime("done", (event) => seen.push(["done", event]))
	realtime.onRealtime("connect", () => seen.push(["connect"]))
	assert.equal(realtime.hasRealtimeListeners(), true)
	await tick()
	assert.equal(loads, 1)
	assert.equal(socket.url, "http://site.local/site.local")
	assert.deepEqual(socket.options, { autoConnect: false, withCredentials: true, reconnectionAttempts: 5 })
	assert.equal(socket.connects, 1)
	socket.emit("connect")
	socket.emit("done", 7)
	assert.deepEqual(seen, [["connect"], ["done", 7]])
	offDone()
	offDone()
	assert.equal(socket.count("done"), 0)
	assert.equal(await realtime.getSocket(), socket)
	assert.equal(loads, 1)
})

test("an unsubscribe before the client loads never attaches the handler", async () => {
	const socket = fakeSocket()
	const realtime = await realtimeModule(async () => ({ io: () => socket }))
	const off = realtime.onRealtime("done", () => {})
	off()
	assert.equal(realtime.hasRealtimeListeners(), false)
	await tick()
	assert.equal(socket.count("done"), 0)
	assert.equal(socket.connects, 0)
})

test("a failed client load is retried on the next subscription", async () => {
	const socket = fakeSocket()
	let loads = 0
	const realtime = await realtimeModule(async () => {
		loads += 1
		if (loads === 1) throw new TypeError("Failed to fetch dynamically imported module")
		return { io: () => socket }
	})
	realtime.onRealtime("done", () => {})
	await tick()
	assert.equal(socket.count("done"), 0)
	realtime.onRealtime("done", () => {})
	await tick()
	assert.equal(loads, 2)
	assert.equal(socket.count("done"), 1)
	assert.equal(socket.connects, 1)
})

test("filters dialog mounted already open builds its rows like a reopen", async () => {
	const previousWindow = globalThis.window
	globalThis.window = { frappe: {} }
	try { await checkFiltersDialog() } finally { globalThis.window = previousWindow }
})

async function checkFiltersDialog() {
	const modules = { "../../utils/documentValues.js": documentValues }
	for (const name of ["button", "dialog", "inputnumber", "inputtext", "select"]) modules[`primevue/${name}`] = stub(name)
	for (const path of ["./DateField.vue", "./DateTimeField.vue", "./LinkField.vue", "./LinkMultiSelectField.vue", "./MultiSelectField.vue", "./TimeField.vue"]) modules[path] = stub(path)
	const component = loadComponent("frontend/src/components/common/ListviewFilters.vue", modules)
	const fields = [{ fieldname: "name", label: "ID", fieldtype: "Data" }, { fieldname: "lot", label: "Lot", fieldtype: "Data" }]
	const rowCount = (root) => findNodes(root, (node) => node.props?.class === "filter-row").length
	const opened = mountComponent(component, Vue.reactive({ visible: true, doctype: "Entry", fields, modelValue: [["lot", "=", "L1"], ["name", "like", "%A%"]] }))
	await tick()
	assert.equal(rowCount(opened), 2)
	const empty = mountComponent(component, Vue.reactive({ visible: true, doctype: "Entry", fields, modelValue: [] }))
	await tick()
	assert.equal(rowCount(empty), 1)
	const closedProps = Vue.reactive({ visible: false, doctype: "Entry", fields, modelValue: [["lot", "=", "L1"]] })
	const closed = mountComponent(component, closedProps)
	await tick()
	assert.equal(rowCount(closed), 0)
	closedProps.visible = true
	await tick()
	assert.equal(rowCount(closed), 1)
}

test("columns dialog mounted already open shows the current columns", async () => {
	const modules = {
		"../../api/frappe.js": { resetUserListview: async () => {}, saveUserListview: async () => {} },
		"./listColumns.js": listColumns,
		"./orderedDraft.js": orderedDraft,
	}
	for (const name of ["button", "checkbox", "dialog", "inputtext", "message"]) modules[`primevue/${name}`] = stub(name)
	const component = loadComponent("frontend/src/components/common/UserListviewColumns.vue", modules)
	const columns = [{ fieldname: "lot", label: "Lot", fieldtype: "Link", enabled: true }, { fieldname: "qty", label: "Qty", fieldtype: "Float", enabled: false }]
	const checkboxes = (root) => findNodes(root, (node) => node.type === "checkbox")
	const opened = mountComponent(component, Vue.reactive({ visible: true, doctype: "Entry", columns, settingsReady: true }))
	await tick()
	assert.equal(checkboxes(opened).length, 2)
	assert.deepEqual(checkboxes(opened).map((node) => node.props["model-value"]), [true, false])
	const closed = mountComponent(component, Vue.reactive({ visible: false, doctype: "Entry", columns, settingsReady: true }))
	await tick()
	assert.equal(checkboxes(closed).length, 0)
})

async function mountListView({ loadFormField = async () => ({}), bulkUpdates = [] } = {}) {
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: { session: { user: "Administrator" } } }
	const fields = [{ fieldname: "lot", label: "Lot", fieldtype: "Data", in_list_view: 1 }]
	const modules = {
		"vue-router": { useRoute: () => ({ fullPath: "/entries" }) },
		"../../api/frappe.js": {
			...api,
			getMeta: async () => [{ name: "Entry", fields }],
			getActiveWorkflow: async () => null,
			getUserListview: async () => ({ fields: [{ fieldname: "name" }, ...fields], columns: null }),
			getItemFilterValues: async () => ({}),
			getList: async () => [{ name: "ENT-1", lot: "L1" }],
			getCount: async () => 1,
			getCounts: async (doctype, sets) => sets.map(() => 1),
			getBulkEditFields: async () => [{ key: "lot", fieldname: "lot", label: "Lot", fieldtype: "Data" }],
			bulkUpdateField: async (...args) => { bulkUpdates.push(args); return { updated: ["ENT-1"], failures: [] } },
		},
		"./listColumns.js": listColumns,
		"../../utils/listNavigation.js": listNavigation,
		"../../utils/statusTone.js": statusTone,
		"../../utils/prettyDate.js": prettyDate,
		"./listStatusFilters.js": listStatusFilters,
		"./listItemFilters.js": listItemFilters,
		"./asyncListParts.js": { FormField: stub("form-field"), loadFormField, UserListviewColumns: stub("columns-dialog"), ListviewFilters: stub("filters-dialog") },
	}
	for (const name of ["button", "column", "datatable", "inputtext", "message", "paginator", "select"]) modules[`primevue/${name}`] = stub(name)
	modules["primevue/dialog"] = dialogStub
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue", "./ListviewQuickFilters.vue"]) modules[path] = stub(path)
	const root = mountComponent(loadComponent("frontend/src/components/common/ListView.vue", modules), Vue.reactive({ doctype: "Entry", navigationEnabled: false }))
	for (let index = 0; index < 4; index += 1) await tick()
	return {
		root,
		find: (type) => findNodes(root, (node) => node.type === type)[0],
		button: (label) => findNodes(root, (node) => node.type === "button" && String(node.props.label || "").startsWith(label))[0],
		restore: () => { globalThis.window = previousWindow },
	}
}

test("ListView mounts the filter and column dialogs on first open and keeps them mounted", async () => {
	const list = await mountListView()
	try {
		const { find, button } = list
		assert.equal(find("filters-dialog"), undefined)
		assert.equal(find("columns-dialog"), undefined)
		assert.equal(find("form-field"), undefined)
		button("Filters").props.onClick()
		await tick()
		assert.equal(find("filters-dialog").props.visible, true)
		find("filters-dialog").props["onUpdate:visible"](false)
		await tick()
		assert.equal(find("filters-dialog").props.visible, false)
		assert.equal(find("columns-dialog"), undefined)
		button("Columns").props.onClick()
		await tick()
		assert.equal(find("columns-dialog").props.visible, true)
	} finally { list.restore() }
})

test("bulk Update stays disabled and inert until the lazy value editor has loaded", async () => {
	let resolveEditor
	const editor = new Promise((resolve) => { resolveEditor = resolve })
	const bulkUpdates = []
	const list = await mountListView({ loadFormField: () => editor, bulkUpdates })
	try {
		list.find("datatable").props["onUpdate:selection"]([{ name: "ENT-1", lot: "L1" }])
		await tick()
		const edit = list.button("Edit")
		assert.ok(edit, "bulk Edit button")
		edit.props.onClick()
		for (let index = 0; index < 3; index += 1) await tick()
		const update = () => list.button("Update 1 record")
		assert.equal(update().props.disabled, true)
		await update().props.onClick()
		assert.deepEqual(bulkUpdates, [])
		resolveEditor({})
		for (let index = 0; index < 3; index += 1) await tick()
		assert.equal(update().props.disabled, false)
		await update().props.onClick()
		assert.equal(bulkUpdates.length, 1)
	} finally { list.restore() }
})
