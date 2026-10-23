import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import test from "node:test"
import { fileURLToPath, pathToFileURL } from "node:url"

import { Vue, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import { stageNewDocumentDefaults } from "../src/utils/newDocumentDefaults.js"

const { parse } = (await import("node:module")).createRequire(new URL("../package.json", import.meta.url))("@vue/compiler-sfc")
const source = resolve(dirname(fileURLToPath(import.meta.url)), "../src/departments")
const tick = async () => { for (let index = 0; index < 4; index += 1) { await new Promise((done) => setImmediate(done)); await Vue.nextTick() } }
const LIST_PATH = "/list?lot=L-1"
const stub = () => null

async function resolveImports(code, filename, modules) {
	const bindings = []
	for (const [statement, names, specifier] of code.matchAll(/^import\s+([\s\S]*?)\s+from\s+["']([^"']+)["']\s*;?$/gm)) {
		const target = specifier.endsWith(".vue") ? { default: stub }
			: modules[specifier] || await import(pathToFileURL(resolve(dirname(filename), specifier)).href)
		const binding = names.startsWith("{") ? names.replace(/\bas\b/g, ":") : names.startsWith("*") ? names.replace(/^\*\s+as\s+/, "") : `{ default: ${names} }`
		bindings.push([statement, `const ${binding} = __modules[${JSON.stringify(specifier)}];`, specifier, names.startsWith("*") ? target : { ...target }])
	}
	let body = code.replace(/^import\s+["'][^"']+["']\s*;?$/gm, "")
	const resolved = {}
	for (const [statement, replacement, specifier, target] of bindings) {
		body = body.replace(statement, replacement)
		resolved[specifier] = target
	}
	return { body: body.replace(/^export /gm, ""), resolved }
}

function baseModules(route) {
	return {
		vue: Vue,
		"vue-router": { useRoute: () => route, useRouter: () => ({ push: async () => {}, replace: async () => {} }), onBeforeRouteLeave() {}, onBeforeRouteUpdate() {} },
		"primevue/usetoast": { useToast: () => ({ add() {} }) },
	}
}

/** Runs a composable or `<script setup>` inside a mounted component and returns `expose()`'s values. */
async function run(path, { route, modules, props = {}, expose }) {
	const filename = resolve(source, path)
	const text = readFileSync(filename, "utf8")
	const code = path.endsWith(".vue") ? parse(text).descriptor.scriptSetup.content : text
	const allModules = { ...baseModules(route), ...modules }
	for (const name of ["button", "select", "checkbox", "column", "datatable", "inputnumber", "inputtext", "message", "skeleton"]) allModules[`primevue/${name}`] ||= { default: stub }
	const { body, resolved } = await resolveImports(code, filename, allModules)
	const factory = new Function("__modules", "defineProps", "defineEmits", `${body}\nreturn (${expose})`)
	let state = null
	const app = mountComponent({ setup() { state = factory(resolved, () => props, () => () => {}); return () => null } }, {})
	await tick()
	return { state, app }
}

function stage(doctype, values) {
	globalThis.window = { history: { state: { back: LIST_PATH, current: "/new" } }, setTimeout, clearTimeout, addEventListener() {}, removeEventListener() {} }
	stageNewDocumentDefaults(doctype, values, LIST_PATH)
}

const newRoute = (name = "new", query = {}) => ({ name, query, params: {}, hash: "" })

for (const [path, apiPath, loader] of [
	["purchase/lot/useLotEditor.js", "../../../api/purchase.js", "getLotForm"],
	["merch/lot/useMerchLotEditor.js", "../../../api/merch.js", "getMerchLotEditor"],
]) {
	test(`${path} prefills list filters into a new Lot; Production Order context and server values win`, async () => {
		stage("SD YRP Lot", { production_order: "PO-1", item: "FILTER-ITEM", status: "Closed", lot_name: "L-NEW", not_in_form: "X" })
		const api = {
			[loader]: async () => ({ record: {}, values: { lot_name: "", production_order: "", item: "", status: "Open", lot_fabric_details: [] }, fields: [], derived: {}, item_details: null, order_item_details: [] }),
			getLotProductionOrderItem: async () => ({ item: "PO-ITEM" }),
		}
		const { state } = await run(path, {
			route: newRoute(),
			modules: {
				"../../../api/frappe.js": { getMeta: async () => [{ name: "SD YRP Lot Fabric Detail" }] },
				"../../../api/purchase.js": { ...(await import("../src/api/purchase.js")), ...(apiPath.endsWith("purchase.js") ? api : { getLotProductionOrderItem: api.getLotProductionOrderItem }) },
				...(apiPath.endsWith("merch.js") ? { "../../../api/merch.js": { ...(await import("../src/api/merch.js")), ...api } } : {}),
			},
			expose: path.includes("Merch") ? "useMerchLotEditor(\"\")" : "useLotEditor(\"\")",
		})
		assert.equal(state.loadError.value, "")
		assert.equal(state.form.production_order, "PO-1")
		assert.equal(state.form.lot_name, "L-NEW")
		assert.equal(state.form.item, "PO-ITEM")
		assert.equal(state.form.status, "Open")
		assert.equal("not_in_form" in state.form, false)
	})
}

test("a Lot opened as a duplicate ignores and clears the staged filters", async () => {
	stage("SD YRP Lot", { lot_name: "L-NEW" })
	const { state } = await run("purchase/lot/useLotEditor.js", {
		route: newRoute("new", { duplicate_from: "LOT-1" }),
		modules: {
			"../../../api/frappe.js": { getMeta: async () => [{ name: "SD YRP Lot Fabric Detail" }] },
			"../../../api/purchase.js": { ...(await import("../src/api/purchase.js")), getLotForm: async () => ({ record: {}, values: { lot_name: "" }, fields: [], derived: {} }) },
		},
		expose: "useLotEditor(\"\")",
	})
	assert.equal(state.form.lot_name, "")
})

test("a new IPD takes the list filters as dirty draft values without overwriting server values", async () => {
	stage("YRP Item Production Detail", { item: "ITEM-1", version: "V9", tech_pack_version: "T1" })
	const { state } = await run("merch/ipd/useIpdEditor.js", {
		route: newRoute(),
		modules: { "../../../api/merch.js": { ...(await import("../src/api/merch.js")), getIpdEditor: async () => ({ record: {}, values: { item: "", version: "V1", tech_pack_version: "" }, capabilities: {}, fields: {} }) } },
		expose: "useIpdEditor(\"\")",
	})
	assert.equal(state.draft.item, "ITEM-1")
	assert.equal(state.draft.tech_pack_version, "T1")
	assert.equal(state.draft.version, "V1")
	assert.equal(state.isDirty.value, true)
})

test("a new Process Cost sends the Lot filter to the server and fills empty editable fields", async () => {
	stage("YRP Process Cost", { lot: "LOT-9", supplier: "SUP-1", is_rework: 1, item: "FILTER-ITEM", process_name: "Dyeing" })
	const requests = []
	const { state } = await run("merch/process-cost/ProcessCostEditor.vue", {
		route: newRoute(),
		modules: {
			"../../../api/frappe.js": { getDoc: async () => ({ supplier_name: "Supplier One" }) },
			"../../../api/merch.js": {
				getProcessCostEditor: async (...args) => { requests.push(args); return { values: { lot: args[1], item: "LOT-ITEM", process_name: "Knitting", supplier: "", is_rework: 0, attribute: "", process_cost_values: [] }, context: { attribute_values: [] }, fields: [] } },
				getProcessCostGrid: async () => ({ attribute_values: [], item: "LOT-ITEM", uom: "Nos" }),
				saveProcessCost: async () => ({}), searchProcessCostAttributes: async () => ({}),
			},
		},
		expose: "{ form }",
	})
	assert.deepEqual(requests[0], [null, "LOT-9", null])
	assert.equal(state.form.lot, "LOT-9")
	assert.equal(state.form.item, "LOT-ITEM")
	assert.equal(state.form.process_name, "Knitting")
	assert.equal(state.form.supplier, "SUP-1")
	assert.equal(state.form.supplier_name, "Supplier One")
	assert.equal(state.form.is_rework, 1)
})

test("a new Item fills empty master fields from the list filters", async () => {
	stage("Item", { item_group: "Fabric", brand: "B-1", stock_uom: "Kg" })
	const { state } = await run("purchase/ItemEditorPage.vue", {
		route: newRoute(),
		modules: { "../../api/purchase.js": { ...(await import("../src/api/purchase.js")), getItemEditor: async () => ({ values: { item_group: "", brand: "", stock_uom: "Nos", attributes: [] }, permissions: { can_create: true } }) } },
		expose: "{ form }",
	})
	assert.equal(state.form.item_group, "Fabric")
	assert.equal(state.form.brand, "B-1")
	assert.equal(state.form.stock_uom, "Nos")
})

test("a new Item Price loads the filtered Item and Supplier as its context and fills other fields", async () => {
	stage("YRP Item Price", { item_name: "ITEM-1", supplier: "SUP-1", tax: "GST 5", uom: "Kg" })
	const requests = []
	const { state } = await run("purchase/ItemPriceEditor.vue", {
		route: newRoute(),
		modules: { "../../api/purchase.js": { ...(await import("../src/api/purchase.js")), getItemPriceEditor: async (...args) => { requests.push(args); return { values: { uom: "Nos" }, attributes: [] } } } },
		expose: "{ form }",
	})
	assert.deepEqual(requests[0], [null, "ITEM-1", null])
	assert.equal(state.form.item_name, "ITEM-1")
	assert.equal(state.form.supplier, "SUP-1")
	assert.equal(state.form.tax, "GST 5")
	assert.equal(state.form.uom, "Nos")
})

test("a new Product fills empty fields from the list filters; a copy does not", async () => {
	const modules = {
		"../../api/frappe.js": { getMeta: async () => [] },
		"../../api/pd.js": { ...(await import("../src/api/pd.js")), getNewProductDefaults: async () => ({ record: { brand: "", category: "Kids" }, permissions: { can_create: true } }), getProductWorkspace: async () => ({ record: { brand: "SRC" } }) },
	}
	stage("SD YRP Product", { brand: "B-1", category: "Men" })
	const { state } = await run("pd/ProductPage.vue", { route: newRoute("pd-product-new"), modules, expose: "{ form }" })
	assert.equal(state.form.value.brand, "B-1")
	assert.equal(state.form.value.category, "Kids")
	stage("SD YRP Product", { category: "Men" })
	const copy = await run("pd/ProductPage.vue", { route: newRoute("pd-product-new", { copy: "P-1" }), modules, expose: "{ form }" })
	assert.notEqual(copy.state.form.value.category, "Men")
})

const { LOTWISE_SECTIONS, LOTWISE_TABLE_COLUMNS } = await import("../src/departments/pd/pdViews.js")
const lotwiseMetadata = [
	{ name: "SD YRP Lotwise Item Profit", fields: [...new Set(Object.values(LOTWISE_SECTIONS).flat())].map((fieldname) => ({ fieldname, options: fieldname })) },
	...Object.entries(LOTWISE_TABLE_COLUMNS).map(([name, columns]) => ({ name, fields: columns.map((fieldname) => ({ fieldname })) })),
]

test("a new Lotwise Item Profit loads the filtered Product on the server and fills empty fields", async () => {
	stage("SD YRP Lotwise Item Profit", { product: "PROD-1", lot: "LOT-1", gst: 12 })
	const requests = []
	const { state } = await run("pd/LotwiseItemProfitPage.vue", {
		route: newRoute("pd-lotwise-item-profit-new"),
		modules: {
			"../../api/frappe.js": { getMeta: async () => lotwiseMetadata },
			"../../api/pd.js": { ...(await import("../src/api/pd.js")), getLotwiseWorkspace: async (args) => { requests.push(args); return { record: { product: args.product, lot: "", gst: 5 }, permissions: { can_create: true } } } },
			"../../composables/usePageTitle.js": { usePageTitle() {} },
		},
		expose: "{ form, loadError }",
	})
	assert.equal(state.loadError.value, "")
	assert.equal(requests[0].product, "PROD-1")
	assert.equal(state.form.value.product, "PROD-1")
	assert.equal(state.form.value.lot, "LOT-1")
	assert.equal(state.form.value.gst, 5)
})
