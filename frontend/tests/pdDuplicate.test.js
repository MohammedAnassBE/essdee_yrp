import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import * as Vue from "vue"
import * as pdViews from "../src/departments/pd/pdViews.js"
import { findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const { LOTWISE_SECTIONS, LOTWISE_TABLE_COLUMNS, PD_ROUTES, copiedLotwiseDraft, copiedProductDraft } = pdViews
const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const identity = {
	name: "source-row", parent: "SOURCE", parenttype: "SD YRP Lotwise Item Profit",
	parentfield: "qty_rate_chart", idx: 8, doctype: "Child", docstatus: 1,
	owner: "source@example.invalid", modified_by: "source@example.invalid",
	creation: "2026-01-01", modified: "2026-02-01", amended_from: "OLD",
}
const rows = {
	qty_rate_chart: [{ size: "M", qty: 100, rate: 200, weight: 0.2, group_index: 1, ratio: 2 }],
	cloth_value: [{ yarn: "Cotton", qty: 20, rate: 100, knitting_cost: 10, dyeing_cost: 20, compacting_cost: 5, wastage_allowance: 3, gsm: 180, ratio: 2 }],
	piece_cloth_weight: [{ size: "M", cloth_group: "Cotton", weight: 0.2 }],
	cmt: [{ costing_name: "Stitching", cost: 15 }],
	packing_materials: [{ costing_name: "Bag", cost: 2 }],
	trims: [{ costing_name: "Button", cost: 1 }],
	trade_discounts: [{ costing_name: "Dealer", based_on: "Selling Price", rate: 5 }],
	other_costs: [{ costing_name: "Transport", based_on: "Cost Price", rate: 2 }],
}
const sourceRecord = {
	...identity, name: "SOURCE", product: "PRODUCT", item: "", lot: "LOT-1",
	lot_costing_type: "Costing", disabled: 0, gst: 5, additional_rate: 10,
	production_cost_template: "Production", trade_discounts_template: "Discounts", other_costs_template: "Other",
	total_qty: 999, profit: 999,
	...Object.fromEntries(Object.entries(rows).map(([table, values]) => [
		table, values.map((row) => ({ ...identity, ...row, net_rate: 999, total_cost: 999, total: 999 })),
	])),
}

function setupPage(filename, route, bindings = {}) {
	const source = read(`../src/departments/pd/${filename}.vue`)
		.split("<script setup>")[1].split("</script>")[0]
		.replace(/^import[\s\S]*? from "[^"]+"\n/gm, "")
		.replace(/^import "[^"]+"\n/gm, "")
	const watches = []
	const values = {
		ref: Vue.ref, computed: Vue.computed, nextTick: Vue.nextTick, ...pdViews,
		watch: (getter, callback) => watches.push({ getter, callback }),
		onMounted() {}, onBeforeUnmount() {}, onBeforeRouteLeave() {}, onBeforeRouteUpdate() {},
		defineProps: () => ({ profitId: "SOURCE", productId: "PRODUCT" }),
		useRoute: () => route, useRouter: () => ({ push() {}, replace() {} }),
		...bindings,
	}
	return {
		...new Function(...Object.keys(values), `${source}\nreturn { form, workspace, loading, loadError, actionError, documentActions, load, save }`)(...Object.values(values)),
		watches,
	}
}

const metadata = [
	{
		name: "SD YRP Lotwise Item Profit",
		fields: [...new Set(Object.values(LOTWISE_SECTIONS).flat())].map((fieldname) => ({ fieldname, options: fieldname })),
	},
	...Object.entries(LOTWISE_TABLE_COLUMNS).map(([name, columns]) => ({ name, fields: columns.map((fieldname) => ({ fieldname })) })),
]

function lotwisePage(route, bindings = {}) {
	return setupPage("LotwiseItemProfitPage", route, {
		getMeta: async () => metadata,
		getLotwiseWorkspace: async ({ name }) => name
			? { record: sourceRecord, modified: "source-timestamp", permissions: { can_create: true, can_write: false } }
			: { record: { gst: 5 }, permissions: { can_create: true } },
		...bindings,
	})
}

test("Lotwise copy retains editable values and every child table without identities or computed values", () => {
	const original = structuredClone(sourceRecord)
	const draft = copiedLotwiseDraft({ gst: 0 }, sourceRecord)
	for (const key of Object.keys(identity)) assert.equal(Object.hasOwn(draft, key), false, key)
	assert.equal(Object.hasOwn(draft, "profit"), false)
	assert.equal(Object.hasOwn(draft, "total_qty"), false)
	for (const [table, expected] of Object.entries(rows)) assert.deepEqual(draft[table], expected)
	for (const field of Object.values(LOTWISE_SECTIONS).flat().filter((key) => !LOTWISE_TABLE_COLUMNS[key])) {
		assert.equal(draft[field], sourceRecord[field], field)
	}
	draft.qty_rate_chart[0].qty = 200
	assert.deepEqual(sourceRecord, original)
	assert.deepEqual(copiedLotwiseDraft({ gst: 5 }, {}), { gst: 5 })
	assert.deepEqual(copiedLotwiseDraft({}, { qty_rate_chart: null }), { qty_rate_chart: [] })
})

test("Lotwise allows retaining the lot; Product clears its unique Style No", () => {
	const lotwise = JSON.parse(read("../../essdee_yrp/essdee_yrp/doctype/sd_yrp_lotwise_item_profit/sd_yrp_lotwise_item_profit.json"))
	assert.equal(lotwise.autoname, "hash")
	assert.deepEqual(lotwise.fields.filter((field) => field.unique), [])
	assert.equal(copiedLotwiseDraft({}, sourceRecord).lot, "LOT-1")
	const product = JSON.parse(read("../../essdee_yrp/essdee_yrp/doctype/sd_yrp_product/sd_yrp_product.json"))
	assert.equal(product.fields.find((field) => field.fieldname === "style_no").unique, 1)
	assert.equal(copiedProductDraft({}, { style_no: "SOURCE" }).style_no, "")
})

test("Lotwise Duplicate is menu-only, requires create permission and an existing record", async () => {
	const route = Vue.reactive({ name: PD_ROUTES.lotwise, query: {} })
	const pushes = []
	const page = lotwisePage(route, { useRouter: () => ({ push: (target) => pushes.push(target) }) })
	await page.load()
	const duplicate = page.documentActions.value.find((action) => action.key === "duplicate")
	assert.equal(duplicate.label, "Duplicate")
	assert.equal(duplicate.icon, "pi pi-copy")
	assert.equal(duplicate.menuOnly, true)
	assert.equal(duplicate.disabled, false)
	duplicate.command()
	assert.deepEqual(pushes, [{ name: PD_ROUTES.lotwiseNew, query: { copy: "SOURCE" } }])
	page.loading.value = true
	assert.equal(page.documentActions.value[0].disabled, true)
	page.workspace.value.permissions = { can_create: false, can_delete: true }
	assert.deepEqual(page.documentActions.value.map((action) => action.key), ["delete"])
	page.workspace.value.permissions.can_create = true
	route.name = PD_ROUTES.lotwiseNew
	assert.deepEqual(page.documentActions.value, [])
	route.name = PD_ROUTES.lotwise
	page.form.value = {}
	assert.deepEqual(page.documentActions.value, [])
})

test("Lotwise copy loads fresh permissions, watches copy changes and saves as a new record", async () => {
	const route = Vue.reactive({ name: PD_ROUTES.lotwiseNew, query: { copy: "SOURCE" } })
	const calls = []
	const page = lotwisePage(route, {
		saveLotwiseItemProfit: async (values, options) => {
			calls.push({ values, options })
			return { record: { ...values, name: "NEW" }, permissions: { can_write: true } }
		},
	})
	await page.load()
	assert.equal(page.loadError.value, "")
	assert.equal(page.form.value.name, undefined)
	assert.deepEqual(page.form.value.qty_rate_chart, rows.qty_rate_chart)
	assert.equal(page.workspace.value.modified, "")
	assert.deepEqual(page.workspace.value.permissions, { can_create: true })
	const watcher = page.watches.at(-1)
	const before = watcher.getter()
	route.query.copy = "SECOND"
	assert.notDeepEqual(watcher.getter(), before)
	assert.equal(watcher.callback, page.load)
	await page.save()
	assert.equal(page.actionError.value, "")
	assert.deepEqual(calls[0].options, { name: null, expectedModified: null })
	assert.deepEqual(calls[0].values, copiedLotwiseDraft({}, sourceRecord))
	route.query = {}
	await page.load()
	assert.deepEqual(page.form.value, { gst: 5 })
	route.name = PD_ROUTES.lotwise
	route.query.copy = "IGNORED"
	await page.load()
	assert.equal(page.form.value.name, "SOURCE")
})

test("Product Duplicate keeps its existing route, prefill and new-document save flow", async () => {
	const route = Vue.reactive({ name: PD_ROUTES.product, query: {} })
	const pushes = []
	const saves = []
	const record = { name: "PRODUCT", style_no: "PRODUCT", item_name: "Shirt", sizes: [{ ...identity, attribute_value: "SIZE-M", size: "M" }] }
	const page = setupPage("ProductPage", route, {
		getMeta: async () => [],
		getNewProductDefaults: async () => ({ record: {}, permissions: { can_create: true } }),
		getProductWorkspace: async () => ({ record, permissions: { can_create: true } }),
		useRouter: () => ({ push: (target) => pushes.push(target) }),
		saveProduct: async (values, images, options) => {
			saves.push({ values, options })
			return { record: { ...values, name: "NEW-PRODUCT" } }
		},
	})
	await page.load()
	page.documentActions.value.find((action) => action.key === "duplicate").command()
	assert.deepEqual(pushes[0], { name: PD_ROUTES.productNew, query: { copy: "PRODUCT" } })
	page.workspace.value.permissions.can_create = false
	assert.equal(page.documentActions.value.some((action) => action.key === "duplicate"), false)
	Object.assign(route, pushes[0])
	await page.load()
	assert.equal(page.loadError.value, "")
	assert.equal(page.form.value.name, undefined)
	assert.equal(page.form.value.style_no, "")
	assert.equal(page.form.value.item_name, "Shirt")
	assert.equal(page.form.value.sizes[0].name, undefined)
	assert.equal(page.form.value.sizes[0].attribute_value, "SIZE-M")
	assert.equal(page.watches.at(-1).getter().at(-1), "PRODUCT")
	page.form.value.style_no = "NEW-PRODUCT"
	await page.save()
	assert.equal(page.actionError.value, "")
	assert.deepEqual(saves[0].options, { name: null, expectedModified: null })
	assert.equal(saves[0].values.sizes[0].size, undefined)
	assert.equal(pushes.at(-1), "/pd/products/NEW-PRODUCT")
})

test("Product header hides document actions for the new form", () => {
	const header = loadComponent(new URL("../src/departments/pd/components/ProductWorkspaceHeader.vue", import.meta.url).pathname, {
		"primevue/button": () => null,
		"../../../components/documents/CustomPrintButtons.vue": () => null,
		"../../../components/documents/DocumentPrintButton.vue": () => null,
		"../../../components/documents/DocumentSaveButton.vue": () => null,
		"../../../components/documents/DocumentActionStrip.vue": () => Vue.h("actions"),
	})
	for (const mode of ["edit", "view"]) {
		const root = mountComponent(header, { record: {}, actions: [{ key: "duplicate" }], printFormats: [], mode })
		assert.equal(findNodes(root, (node) => node.type === "actions").length, mode === "edit" ? 0 : 1)
	}
})

test("Lotwise route switches discard late copy responses and source errors clear the form", async () => {
	const route = Vue.reactive({ name: PD_ROUTES.lotwiseNew, query: { copy: "SOURCE" } })
	let resolveSource
	const pending = new Promise((resolve) => { resolveSource = resolve })
	const page = lotwisePage(route, {
		getLotwiseWorkspace: async ({ name }) => name ? pending : { record: { gst: 5 }, permissions: { can_create: true } },
	})
	const oldLoad = page.load()
	route.query.copy = ""
	await page.load()
	resolveSource({ record: sourceRecord })
	await oldLoad
	assert.deepEqual(page.form.value, { gst: 5 })
	route.query.copy = "DENIED"
	const denied = lotwisePage(route, {
		getLotwiseWorkspace: async ({ name }) => {
			if (name) throw new Error("Not permitted")
			return { record: {}, permissions: { can_create: true } }
		},
	})
	await denied.load()
	assert.equal(denied.loadError.value, "Not permitted")
	assert.deepEqual(denied.form.value, {})
	assert.deepEqual(denied.documentActions.value, [])
})
