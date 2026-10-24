import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as listColumns from "../src/components/common/listColumns.js"
import * as listNavigation from "../src/utils/listNavigation.js"
import * as statusTone from "../src/utils/statusTone.js"
import * as prettyDate from "../src/utils/prettyDate.js"
import * as listStatusFilters from "../src/components/common/listStatusFilters.js"
import * as listItemFilters from "../src/components/common/listItemFilters.js"
import { isClickFilterColumn, replaceEqualityFilter } from "../src/components/common/listClickFilters.js"
import { equalityFilterDefaults, stageNewDocumentDefaults, takeNewDocumentDefaults, withNewDocumentDefaults } from "../src/utils/newDocumentDefaults.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const stub = name => (props, { slots }) => Vue.h(name, props, slots.default?.())
const flatten = vnodes => vnodes.flatMap(vnode => vnode.type === Vue.Fragment ? flatten(vnode.children || []) : [vnode])

function dataTable(props, { slots }) {
	const columns = flatten(slots.default?.() || []).filter(column => column.children?.body)
	return Vue.h("table", {}, (props.value || []).map(row => Vue.h("tr", {
		row: row.name,
		onClick: event => props.onRowClick?.({ originalEvent: event, data: row }),
	}, columns.map(column => Vue.h("td", { field: column.props?.field }, column.children.body({ data: row }))))))
}

const fields = [
	{ fieldname: "supplier", label: "Supplier", fieldtype: "Link", options: "Supplier", in_standard_filter: 1, in_list_view: 1 },
	{ fieldname: "lot", label: "Lot", fieldtype: "Link", options: "SD YRP Lot", in_list_view: 1 },
	{ fieldname: "status", label: "Status", fieldtype: "Select", options: "Draft\nOpen\nClosed", in_list_view: 1 },
	{ fieldname: "qty", label: "Qty", fieldtype: "Float", in_list_view: 1 },
	{ fieldname: "posting_date", label: "Date", fieldtype: "Date", in_list_view: 1 },
	{ fieldname: "total", label: "Total", fieldtype: "Float", read_only: 1 },
	{ fieldname: "items", label: "Items", fieldtype: "Table", options: "Entry Item" },
]
const rows = [{ name: "ENT-1", supplier: "Acme", lot: "LOT-1", status: "Open", qty: 4, posting_date: "2026-10-01", modified: "2026-10-01 10:00:00" }]

async function mountList(props = {}) {
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: {}, history: { state: { current: "/entries" } } }
	const calls = { lists: [] }
	const api = {
		getMeta: async () => [{ name: "Entry", fields }, { name: "Entry Item", fields: [{ fieldname: "item", fieldtype: "Link", options: "Item" }] }],
		getActiveWorkflow: async () => null,
		getUserListview: async () => ({ fields: [{ fieldname: "name" }, ...fields], columns: null }),
		getItemFilterValues: async () => ({}),
		getList: async (doctype, args) => { calls.lists.push(args.filters); return rows },
		getCount: async () => rows.length,
		getCounts: async (doctype, filterSets) => filterSets.map(() => rows.length),
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
	for (const name of ["button", "dialog", "inputtext", "message", "paginator", "select"]) modules[`primevue/${name}`] = stub(name)
	modules["primevue/column"] = stub("column")
	modules["primevue/datatable"] = dataTable
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue"]) modules[path] = stub(path)
	modules["./asyncListParts.js"] = { FormField: stub("./FormField.vue"), UserListviewColumns: stub("./UserListviewColumns.vue"), ListviewFilters: stub("advanced-filters") }
	modules["./ListviewQuickFilters.vue"] = stub("quick-filters")
	const opened = []
	const component = loadComponent("frontend/src/components/common/ListView.vue", modules)
	const root = mountComponent(component, Vue.reactive({ doctype: "Entry", navigationEnabled: false, onRowClick: row => opened.push(row.name), ...props }))
	await tick(); await tick(); await tick()
	findNodes(root, node => node.type === "button" && node.props.label === "Filters")[0].props.onClick()
	await tick()
	const cell = (fieldname) => findNodes(root, node => node.type === "td" && node.props.field === fieldname)[0]?.children.find(child => !["text", "comment"].includes(child.type))
	const click = async (fieldname) => {
		let stopped = false
		const event = { target: null, stopPropagation: () => { stopped = true } }
		cell(fieldname).props.onClick?.(event)
		if (!stopped) findNodes(root, node => node.type === "tr")[0].props.onClick(event)
		await tick(); await tick()
	}
	const advanced = () => findNodes(root, node => node.type === "advanced-filters")[0].props.modelValue
	const quick = () => findNodes(root, node => node.type === "quick-filters")[0].props.modelValue
	const toolbar = findNodes(root, node => node.props.class === "list-toolbar__primary")[0]
	return { root, calls, opened, cell, click, advanced, quick, toolbar, restore: () => { globalThis.window = previousWindow } }
}

test("filterable columns follow Desk: name and numbers are skipped", () => {
	assert.equal(isClickFilterColumn({ fieldname: "name", fieldtype: "Data" }), false)
	assert.equal(isClickFilterColumn({ fieldname: "qty", fieldtype: "Float" }), false)
	assert.equal(isClickFilterColumn({ fieldname: "amount", fieldtype: "Currency" }), false)
	for (const fieldtype of ["Link", "Select", "Data", "Check", "Date"]) assert.equal(isClickFilterColumn({ fieldname: "x", fieldtype }), true, fieldtype)
	assert.equal(isClickFilterColumn({ fieldname: "docstatus", fieldtype: "Int" }, { isStatus: true }), true)
})

test("replacing an equality filter keeps other filters on the field", () => {
	const filters = [["lot", "=", "A"], ["Entry", "lot", "=", "B"], ["lot", "like", "%L%"], ["Entry Item", "lot", "=", "C"]]
	assert.deepEqual(replaceEqualityFilter(filters, "Entry", "lot", "D"), [["lot", "like", "%L%"], ["Entry Item", "lot", "=", "C"], ["lot", "=", "D"]])
})

test("clicking a Link value adds an equality filter and reloads; clicking again replaces it", async () => {
	const list = await mountList()
	try {
		assert.match(String(list.cell("lot").props.class), /list-filter-value/)
		assert.doesNotMatch(String(list.cell("qty").props.class), /list-filter-value/)
		await list.click("lot")
		assert.deepEqual(list.advanced(), [["lot", "=", "LOT-1"]])
		assert.deepEqual(list.calls.lists.at(-1), [["lot", "=", "LOT-1"]])
		rows[0].lot = "LOT-2"
		await list.click("lot")
		assert.deepEqual(list.advanced(), [["lot", "=", "LOT-2"]])
		assert.deepEqual(list.opened, [])
	} finally {
		rows[0].lot = "LOT-1"
		list.restore()
	}
})

test("clicking a quick-filter field fills the quick filter instead of an advanced filter", async () => {
	const list = await mountList()
	try {
		await list.click("supplier")
		assert.deepEqual(list.quick(), { supplier: "Acme" })
		assert.deepEqual(list.advanced(), [])
		assert.deepEqual(list.calls.lists.at(-1), [["supplier", "=", "Acme"]])
	} finally {
		list.restore()
	}
})

test("name and numeric cells, and the rest of the row, still open the document", async () => {
	const list = await mountList()
	try {
		await list.click("name")
		await list.click("qty")
		assert.deepEqual(list.opened, ["ENT-1", "ENT-1"])
		assert.deepEqual(list.advanced(), [])
	} finally {
		list.restore()
	}
})

test("a toolbar click stages the visible equality filters for the new document", async () => {
	const list = await mountList({ filters: [["lot", "=", "BASE"]] })
	try {
		await list.click("supplier")
		await list.click("status")
		list.toolbar.props.onClickCapture()
		assert.deepEqual(takeNewDocumentDefaults("Entry", { back: "/entries" }), { supplier: "Acme", status: "Open" })
	} finally {
		list.restore()
	}
})

test("only equality filters on real, editable parent fields become defaults", () => {
	const filters = [
		["supplier", "=", "Acme"],
		["lot", "like", "%A%"],
		["posting_date", "between", ["2026-10-01", "2026-10-31"]],
		["Entry Item", "item", "=", "ITEM-1"],
		["total", "=", 5],
		["name", "=", "ENT-1"],
		["missing", "=", "X"],
		["Entry", "status", "=", "Draft"],
	]
	assert.deepEqual(equalityFilterDefaults(filters, "Entry", [...fields, { fieldname: "virtual_total", fieldtype: "Float", is_virtual: 1 }]), { supplier: "Acme", status: "Draft" })
})

test("staged defaults are one-shot and only reach a form opened from the staging list", () => {
	stageNewDocumentDefaults("Entry", { supplier: "Acme" }, "/entries")
	assert.deepEqual(takeNewDocumentDefaults("Other", { back: "/entries" }), {})
	assert.deepEqual(takeNewDocumentDefaults("Entry", { back: "/elsewhere", current: "/entries/new" }), {})
	stageNewDocumentDefaults("Entry", { supplier: "Acme" }, "/entries")
	assert.deepEqual(takeNewDocumentDefaults("Entry", { back: "/entries", current: "/entries/new" }), { supplier: "Acme" })
	assert.deepEqual(takeNewDocumentDefaults("Entry", { back: "/entries" }), {})
})

test("defaults fill empty fields and unticked checks without overriding computed values", () => {
	const record = { supplier: "", lot: "LOT-9", is_return: 0, location: null }
	assert.deepEqual(withNewDocumentDefaults(record, { supplier: "Acme", lot: "LOT-1", is_return: 1, location: "Main" }), { supplier: "Acme", lot: "LOT-9", is_return: 1, location: "Main" })
})
