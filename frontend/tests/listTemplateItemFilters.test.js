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

for (const enabled of [false, true]) test(`ListView template Item filtering is opt-in (${enabled}) and re-resolves variants on each reload`, async () => {
	const previousWindow = globalThis.window
	globalThis.window = { sessionStorage: { getItem: () => null }, frappe: {} }
	const lookups = [], lists = [], counts = []
	const api = {
		getMeta: async () => [{ name: "Entry", fields: [item, { fieldname: "status", fieldtype: "Select", options: "Draft\nSubmitted" }, { fieldname: "items", label: "Items", fieldtype: "Table", options: "Detail" }] }, { name: "Detail", fields: [{ ...item, fieldname: "item_variant" }] }],
		getActiveWorkflow: async () => null,
		getUserListview: async () => ({ fields: [{ fieldname: "name" }, item, { fieldname: "status", fieldtype: "Select" }], columns: null }),
		getItemFilterValues: async items => { lookups.push(items); return { Template: ["Template", "Variant", "Disabled Variant"], Plain: ["Plain"] } },
		getList: async (doctype, args) => { lists.push(args.filters); return [] },
		getCount: async (doctype, filters) => { counts.push(filters); return 0 },
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
	for (const path of ["../documents/DocumentStatusBadge.vue", "../navigation/InlinePageNavigation.vue", "./FormField.vue", "./UserListviewColumns.vue"]) modules[path] = stub(path)
	modules["./ListviewFilters.vue"] = stub("advanced-filters")
	modules["./ListviewQuickFilters.vue"] = stub("quick-filters")
	try {
		const component = loadComponent("frontend/src/components/common/ListView.vue", modules)
		const props = Vue.reactive({ doctype: "Entry", templateItemFilters: enabled, navigationEnabled: false, initialAdvancedFilters: [["Detail", "item_variant", "=", "Template"], ["item", "=", "Plain"]], statusField: "status", statusOptions: ["Draft", "Submitted"] })
		const root = mountComponent(component, props)
		await tick(); await tick()
		const advanced = findNodes(root, node => node.type === "advanced-filters")[0]
		const quick = findNodes(root, node => node.type === "quick-filters")[0]
		for (const field of [...advanced.props.fields, ...quick.props.fields].filter(field => field.options === "Item")) {
			assert.deepEqual(field.link_filters || {}, enabled ? { variant_of: ["is", "not set"] } : {})
		}
		const expected = ["Detail", "item_variant", enabled ? "in" : "=", enabled ? ["Template", "Variant", "Disabled Variant"] : "Template"]
		assert.deepEqual(lists[0][0], expected)
		assert.deepEqual(lists[0][1], ["item", enabled ? "in" : "=", enabled ? ["Plain"] : "Plain"])
		assert.ok(counts.length > 1)
		assert.ok(counts.every(filters => JSON.stringify(filters[0]) === JSON.stringify(expected)))
		props.initialAdvancedFilters = [["Detail", "item_variant", "!=", "Template"], ["item", "=", "Plain"]]
		await tick(); await tick()
		assert.equal(lookups.length, enabled ? 2 : 0)
		if (enabled) assert.deepEqual(lookups, [["Template", "Plain"], ["Template", "Plain"]])
		assert.equal(lists.at(-1)[0][2], enabled ? "not in" : "!=")
	} finally { globalThis.window = previousWindow }
})
