import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as listColumns from "../src/components/common/listColumns.js"
import * as listNavigation from "../src/utils/listNavigation.js"
import * as statusTone from "../src/utils/statusTone.js"
import * as prettyDate from "../src/utils/prettyDate.js"
import * as listStatusFilters from "../src/components/common/listStatusFilters.js"
import * as listItemFilters from "../src/components/common/listItemFilters.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const stub = name => (props) => Vue.h(name, props)
const item = { fieldname: "item", label: "Item", fieldtype: "Link", options: "Item", in_standard_filter: 1 }
const templateOnly = { variant_of: ["is", "not set"] }

async function mountList(props, metas, listviewFields = [{ fieldname: "name" }, item, { fieldname: "status", fieldtype: "Select" }]) {
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: {} }
	const calls = { lookups: [], lists: [], counts: [] }
	const api = {
		getMeta: async () => metas,
		getActiveWorkflow: async () => null,
		getUserListview: async () => ({ fields: listviewFields, columns: null }),
		getItemFilterValues: async items => { calls.lookups.push(items); return { Template: ["Template", "Variant", "Disabled Variant"], Plain: ["Plain"] } },
		getList: async (doctype, args) => { calls.lists.push(args.filters); return [] },
		getCount: async (doctype, filters) => { calls.counts.push(filters); return 0 },
		getCounts: async (doctype, filterSets) => { calls.counts.push(...filterSets); return filterSets.map(() => 0) },
	}
	const modules = {
		"vue-router": { useRoute: () => ({ fullPath: "/stock" }) },
		"../../api/frappe.js": api,
		"./listColumns.js": listColumns,
		"../../utils/listNavigation.js": listNavigation,
		"../../utils/statusTone.js": statusTone,
		"../../utils/prettyDate.js": prettyDate,
		"./listStatusFilters.js": listStatusFilters,
		"./listItemFilters.js": listItemFilters,
	}
	for (const name of ["button", "column", "datatable", "dialog", "inputtext", "message", "paginator", "select"]) modules[`primevue/${name}`] = stub(name)
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue"]) modules[path] = stub(path)
	modules["./asyncListParts.js"] = { FormField: stub("./FormField.vue"), UserListviewColumns: stub("./UserListviewColumns.vue"), ListviewFilters: stub("advanced-filters") }
	modules["./ListviewQuickFilters.vue"] = stub("quick-filters")
	try {
		const component = loadComponent("frontend/src/components/common/ListView.vue", modules)
		const reactiveProps = Vue.reactive({ navigationEnabled: false, ...props })
		const root = mountComponent(component, reactiveProps)
		await tick(); await tick()
		findNodes(root, node => node.type === "button" && node.props.label === "Filters")[0].props.onClick()
		await tick()
		const advanced = findNodes(root, node => node.type === "advanced-filters")[0]
		const quick = findNodes(root, node => node.type === "quick-filters")[0]
		const itemFields = [...advanced.props.fields, ...(quick?.props.fields || [])].filter(field => field.fieldtype === "Link" && field.options === "Item")
		return { ...calls, itemFields, props: reactiveProps, restore: () => { globalThis.window = previousWindow } }
	} catch (error) {
		globalThis.window = previousWindow
		throw error
	}
}

const entryMetas = [{ name: "Entry", fields: [item, { fieldname: "status", fieldtype: "Select", options: "Draft\nSubmitted" }, { fieldname: "items", label: "Items", fieldtype: "Table", options: "Detail" }] }, { name: "Detail", fields: [{ ...item, fieldname: "item_variant" }] }]

test("every ListView Item filter suggests only templates and plain items and expands templates to variants", async () => {
	const list = await mountList({ doctype: "Entry", initialAdvancedFilters: [["Detail", "item_variant", "=", "Template"], ["item", "=", "Plain"]], statusField: "status", statusOptions: ["Draft", "Submitted"] }, entryMetas)
	try {
		assert.ok(list.itemFields.length >= 3)
		for (const field of list.itemFields) assert.deepEqual(field.link_filters, templateOnly)
		const expected = ["Detail", "item_variant", "in", ["Template", "Variant", "Disabled Variant"]]
		assert.deepEqual(list.lists[0][0], expected)
		assert.deepEqual(list.lists[0][1], ["item", "in", ["Plain"]])
		assert.ok(list.counts.length > 1)
		assert.ok(list.counts.every(filters => JSON.stringify(filters[0]) === JSON.stringify(expected)))
		list.props.initialAdvancedFilters = [["Detail", "item_variant", "!=", "Template"], ["item", "=", "Plain"]]
		await tick(); await tick()
		assert.deepEqual(list.lookups, [["Template", "Plain"], ["Template", "Plain"]])
		assert.equal(list.lists.at(-1)[0][2], "not in")
	} finally { list.restore() }
})

test("Item filter keeps a field's own link filters alongside the template rule", async () => {
	const stockItem = { ...item, link_filters: '[["Item","is_stock_item","=",1]]' }
	const metas = [{ name: "Entry", fields: [stockItem, { ...item, fieldname: "fabric", label: "Fabric", in_standard_filter: 0 }] }]
	const list = await mountList({ doctype: "Entry", linkFilters: { fabric: { has_variants: 1 } } }, metas, [{ fieldname: "name" }, stockItem])
	try {
		for (const field of list.itemFields) {
			assert.deepEqual(field.link_filters, field.fieldname === "item" ? { is_stock_item: 1, ...templateOnly } : { has_variants: 1, ...templateOnly })
		}
		assert.deepEqual(list.itemFields.map(field => field.fieldname).sort(), ["fabric", "item", "item"])
	} finally { list.restore() }
})

test("Item ListView never lists Item Variants and its ID filter suggests only templates and plain items", async () => {
	const list = await mountList({ doctype: "Item", filters: [["disabled", "=", 0]] }, [{ name: "Item", fields: [{ fieldname: "item_group", fieldtype: "Link", options: "Item Group" }] }])
	try {
		assert.ok(list.lists.length && list.counts.length)
		for (const filters of [...list.lists, ...list.counts]) assert.ok(filters.some(filter => JSON.stringify(filter) === JSON.stringify(["variant_of", "is", "not set"])), JSON.stringify(filters))
		const id = list.itemFields.find(field => field.fieldname === "name")
		assert.deepEqual(id.link_filters, templateOnly)
	} finally { list.restore() }
})
