import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as api from "../src/api/frappe.js"
import * as listBulkActions from "../src/components/common/listBulkActions.js"
import * as listColumns from "../src/components/common/listColumns.js"
import * as listItemFilters from "../src/components/common/listItemFilters.js"
import * as listStatusFilters from "../src/components/common/listStatusFilters.js"
import * as listNavigation from "../src/utils/listNavigation.js"
import * as prettyDate from "../src/utils/prettyDate.js"
import * as statusTone from "../src/utils/statusTone.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const tick = async () => { for (let index = 0; index < 4; index += 1) { await new Promise((resolve) => setImmediate(resolve)); await Vue.nextTick() } }
const stub = (name) => (props, { slots }) => Vue.h(name, props, [slots.default?.(), slots.footer?.()])
const ROWS = [
	{ name: "DC-1", docstatus: 0, modified: "m1" },
	{ name: "DC-2", docstatus: 1, modified: "m2" },
	{ name: "DC-3", docstatus: 1, modified: "m3" },
]

async function mountList({ user = "Administrator", boot = {}, calls = [], failures = {}, workflow = null } = {}) {
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: { session: { user }, boot: { user: boot } } }
	let listLoads = 0
	const fail = (name) => { if (failures[name]) throw new Error(failures[name]) }
	const modules = {
		"vue-router": { useRoute: () => ({ fullPath: "/challans" }) },
		"../../api/frappe.js": {
			...api,
			getMeta: async () => [{ name: "YRP Delivery Challan", is_submittable: 1, fields: [] }],
			getActiveWorkflow: async () => workflow,
			getUserListview: async () => ({ fields: [{ fieldname: "name" }, { fieldname: "docstatus" }], columns: null }),
			getItemFilterValues: async () => ({}),
			getList: async () => { listLoads += 1; return ROWS },
			getCount: async () => ROWS.length,
			getCounts: async (doctype, sets) => sets.map(() => 1),
			submitDoc: async (doctype, name, modified) => { calls.push(["submit", name, modified]); fail(name) },
			cancelDoc: async (doctype, name, modified) => { calls.push(["cancel", name, modified]); fail(name) },
			deleteDoc: async (doctype, name) => { calls.push(["delete", name]); fail(name) },
		},
		"./listBulkActions.js": listBulkActions,
		"./listColumns.js": listColumns,
		"../../utils/listNavigation.js": listNavigation,
		"../../utils/statusTone.js": statusTone,
		"../../utils/prettyDate.js": prettyDate,
		"./listStatusFilters.js": listStatusFilters,
		"./listItemFilters.js": listItemFilters,
		"./asyncListParts.js": { FormField: stub("form-field"), loadFormField: async () => ({}), UserListviewColumns: stub("columns-dialog"), ListviewFilters: stub("filters-dialog") },
		"../documents/DocumentConfirmationDialog.vue": stub("confirm-dialog"),
		"./ListBulkResultDialog.vue": stub("result-dialog"),
	}
	for (const name of ["button", "column", "datatable", "inputtext", "menu", "message", "paginator", "select", "dialog"]) modules[`primevue/${name}`] = stub(name)
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue", "./ListviewQuickFilters.vue"]) modules[path] = stub(path)
	const root = mountComponent(loadComponent("frontend/src/components/common/ListView.vue", modules), Vue.reactive({ doctype: "YRP Delivery Challan", title: "Delivery Challans", navigationEnabled: false }))
	await tick()
	const find = (type) => findNodes(root, (node) => node.type === type)[0]
	return {
		find,
		listLoads: () => listLoads,
		select: async (rows) => { find("datatable").props["onUpdate:selection"](rows); await tick() },
		menuLabels: () => (find("menu")?.props.model || []).map((item) => item.label),
		runMenu: async (label) => { find("menu").props.model.find((item) => item.label.startsWith(label)).command(); await tick() },
		restore: () => { globalThis.window = previousWindow },
	}
}

test("selecting rows shows Actions only for docstatuses present in the selection", async () => {
	const list = await mountList()
	try {
		assert.ok(list.find("datatable").props.selection !== undefined)
		assert.equal(list.find("menu"), undefined)
		await list.select([ROWS[1], ROWS[2]])
		assert.deepEqual(list.menuLabels(), ["Edit", "Cancel (2)"])
		await list.select(ROWS)
		assert.deepEqual(list.menuLabels(), ["Edit", "Submit (1)", "Cancel (2)", "Delete (1)"])
	} finally { list.restore() }
})

test("actions follow the user's submit, cancel and delete permissions", async () => {
	const list = await mountList({ user: "clerk@example.com", boot: { can_write: [], can_cancel: ["YRP Delivery Challan"], can_delete: [] } })
	try {
		await list.select(ROWS)
		assert.deepEqual(list.menuLabels(), ["Cancel (2)"])
	} finally { list.restore() }
})

test("a confirmed bulk Cancel runs per document, lists each failure, refreshes and clears the selection", async () => {
	const calls = []
	const list = await mountList({ calls, failures: { "DC-3": "Insufficient stock for Item X in Store" } })
	try {
		await list.select(ROWS)
		await list.runMenu("Cancel")
		const confirm = list.find("confirm-dialog")
		assert.equal(confirm.props.visible, true)
		assert.equal(confirm.props.message, "Cancel 2 Delivery Challans?")
		assert.deepEqual(calls, [])
		const loadsBefore = list.listLoads()
		await confirm.props.onConfirm()
		await tick()
		assert.deepEqual(calls, [["cancel", "DC-2", "m2"], ["cancel", "DC-3", "m3"]])
		const result = list.find("result-dialog")
		assert.equal(result.props.visible, true)
		assert.deepEqual(result.props.outcome.failed, [{ name: "DC-3", error: "Insufficient stock for Item X in Store" }])
		assert.ok(list.listLoads() > loadsBefore, "list refreshed after the action")
		assert.deepEqual(list.find("datatable").props.selection, [])
	} finally { list.restore() }
})

test("bulk Delete removes drafts and cancelled documents through the standard delete", async () => {
	const calls = []
	const list = await mountList({ calls })
	try {
		await list.select([...ROWS, { name: "DC-4", docstatus: 2, modified: "m4" }])
		await list.runMenu("Delete")
		assert.equal(list.find("confirm-dialog").props.message, "Delete 2 Delivery Challans?")
		await list.find("confirm-dialog").props.onConfirm()
		await tick()
		assert.deepEqual(calls, [["delete", "DC-1"], ["delete", "DC-4"]])
		assert.notEqual(list.find("result-dialog")?.props.visible, true)
	} finally { list.restore() }
})

test("workflow doctypes offer no direct Submit or Cancel", async () => {
	const list = await mountList({ workflow: { name: "DC Flow", state_field: "workflow_state", states: [] } })
	try {
		await list.select(ROWS)
		assert.deepEqual(list.menuLabels(), ["Edit", "Delete (1)"])
	} finally { list.restore() }
})

test("related-record dialogs such as Delivery Challans on a Work Order allow bulk actions", () => {
	assert.doesNotMatch(source("../src/components/documents/RelatedRecordsDialog.vue"), /allow-bulk-actions/)
})
