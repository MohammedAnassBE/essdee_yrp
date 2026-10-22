import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockHeaderFields from "../src/departments/fabric-store/stockHeaderFields.js"
import * as fieldErrors from "../src/utils/fieldErrors.js"
import * as linkTarget from "../src/utils/linkTarget.js"
import * as displayGroups from "../src/engine/stock/groupItemsForDisplay.js"
import { getStockUpdateRates } from "../src/api/fabricStore.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const Button = (props) => Vue.h("button", props, props.label)
const Control = (props) => Vue.h("control", props)
const LinkField = (props) => Vue.h("link-field", props)
const Container = (props, { slots }) => Vue.h("container", props, slots.default?.())
const modules = {
	"primevue/button": Button,
	"primevue/message": Container,
	"../../components/common/LinkField.vue": LinkField,
	"../../utils/stockItemComposer.js": stockItemComposer,
	"../../api/frappe.js": { callMethod: async () => [] },
}
const Composer = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemComposer.vue"), modules)
const Matrix = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemMatrix.vue"), {
	"../common/DocumentLink.vue": Control,
	"../../utils/linkTarget.js": linkTarget,
	"../../engine/stock/groupItemsForDisplay.js": displayGroups,
	"../../utils/stockItemComposer.js": stockItemComposer,
})
const textContent = (node) => node.type === "comment" ? "" : node.text + node.children.map(textContent).join("")
const button = (root, label) => findNodes(root, node => node.type === "button" && node.props.label === label)[0]
const editButton = (root) => findNodes(root, node => node.type === "button" && node.props.title === "Edit item")[0]
const quantityInputs = (root) => findNodes(root, node => node.type === "input" && node.props.step === "0.001")
const rateInputs = (root) => findNodes(root, node => node.type === "input" && node.props.step === "0.0001")
const priceTexts = (root) => findNodes(root, node => /(?:item-matrix|stock-composer)__price/.test(node.props.class || "")).map(textContent)
const schemaFor = (layout) => ({ item: "Fabric A", primary_attribute: layout === "grid" ? "Dia" : "", primary_attribute_values: layout === "grid" ? ["58 Dia", "60 Dia"] : [], attributes: layout === "grid" ? ["Dia"] : [], default_uom: "Kg" })
const keysFor = (layout) => layout === "grid" ? ["58 Dia", "60 Dia"] : ["default"]
const groupFor = (layout) => {
	const schema = schemaFor(layout)
	return { ...schema, attributes: [], items: [{ name: schema.item, primary_attribute: schema.primary_attribute, attributes: {}, dimensions: { lot: "LOT-1" }, default_uom: "Kg", values: Object.fromEntries(keysFor(layout).map((key, index) => [key, { qty: index + 2, rate: index ? 0 : 1234.567 }])) }] }
}
function mountComposer(operation, layout, extra = {}, component = Composer) {
	const props = Vue.reactive({ operation, editor: { dimensions: [] }, modelValue: [], schemaLoader: async () => schemaFor(layout), ...extra,
		"onUpdate:modelValue": (value) => { props.modelValue = value },
	})
	return { root: mountComponent(component, props), props }
}
async function fetchItem(root) {
	findNodes(root, node => node.type === "link-field" && node.props.label === "Item *")[0].props["onUpdate:modelValue"]("Fabric A")
	await tick()
	await button(root, "Get Item").props.onClick()
	await tick()
}
async function enterQuantities(root) {
	quantityInputs(root).forEach((input, index) => typeInto(input, index + 2))
	await tick()
}
async function click(root, label) {
	await button(root, label).props.onClick()
	await tick()
}

const stockCases = [
	[1, 6, "stock_entry", "YRP Stock Entry", "Rate"],
	[2, 7, "stock_reconciliation", "YRP Stock Reconciliation", "Rate"],
	[3, 8, "stock_update", "YRP Stock Update", "Valuation Rate"],
	[4, 9, "lot_transfer", "SD YRP Lot Transfer", "Rate"],
]
for (const layout of ["grid", "single"]) {
	for (const [matrixCase, composerCase, operation, doctype, label] of stockCases) {
		test(`case ${matrixCase}: ${doctype} saved rates (${layout})`, () => {
			for (const showPricing of [false, true]) {
				const root = mountComponent(Matrix, { doctype, groups: [groupFor(layout)], showPricing })
				assert.deepEqual(priceTexts(root), layout === "grid" ? [`${label} 1,234.57`, `${label} 0`] : [`${label} 1,234.57`])
				assert.doesNotMatch(textContent(root), /Amount/)
			}
		})
		test(`case ${composerCase}: ${operation} staged rates (${layout})`, () => {
			const { root } = mountComposer(operation, layout, { modelValue: [groupFor(layout)] })
			assert.deepEqual(priceTexts(root), layout === "grid" ? [`${label} 1,234.57`, `${label} 0`] : [`${label} 1,234.57`])
			assert.equal(rateInputs(root).length, 0)
			assert.doesNotMatch(textContent(root), /Amount/)
		})
	}

	test(`case 5: unrelated rates hidden and Purchase Order pricing unchanged (${layout})`, () => {
		assert.deepEqual(priceTexts(mountComponent(Matrix, { doctype: "YRP Work Order", groups: [groupFor(layout)] })), [])
		assert.deepEqual(priceTexts(mountComponent(Matrix, { doctype: "Purchase Order", groups: [groupFor(layout)] })), [])
		const expected = layout === "grid" ? ["Rate INR 1,234.57", "Amount INR 2,469.13", "Rate INR 0", "Amount INR 0", "Amount INR 2,469.13"] : ["Rate INR 1,234.57", "Amount INR 2,469.13"]
		assert.deepEqual(priceTexts(mountComponent(Matrix, { doctype: "Purchase Order", groups: [groupFor(layout)], showPricing: true, currency: "INR" })), expected)
		assert.ok(priceTexts(mountComponent(Matrix, { doctype: "Purchase Order", groups: [groupFor(layout)], showPricing: true, showAmount: false })).every(text => text.startsWith("Rate ")))
		const { root } = mountComposer("purchase_order", layout, { modelValue: [groupFor(layout)], currency: "INR" })
		assert.deepEqual(priceTexts(root), layout === "grid" ? expected : [...expected, "Amount INR 2,469.13"])
	})

	test(`case 10: reconciliation Rate Add and Edit (${layout})`, async () => {
		const { root, props } = mountComposer("stock_reconciliation", layout)
		await fetchItem(root)
		assert.equal(rateInputs(root).length, keysFor(layout).length)
		for (const input of rateInputs(root)) {
			assert.equal(input.props.type, "number")
			assert.match(textContent(input.parent), /Rate/)
			const quantityCell = layout === "grid" ? input.parent : input.parent.parent
			assert.ok(findNodes(quantityCell, node => node.type === "input" && node.props.step === "0.001").length, "rate sits beside its quantity")
			typeInto(input, 17.25)
		}
		await enterQuantities(root)
		await click(root, "OK · Add Item")
		assert.ok(Object.values(props.modelValue[0].items[0].values).every(value => value.rate === 17.25))
		await editButton(root).props.onClick()
		await tick()
		assert.ok(rateInputs(root).every(input => Number(input.value) === 17.25))
		rateInputs(root).forEach(input => typeInto(input, 26.5))
		await click(root, "Update Item")
		assert.equal(props.modelValue[0].items.length, 1)
		assert.ok(Object.values(props.modelValue[0].items[0].values).every(value => value.rate === 26.5))
		assert.ok(priceTexts(root).every(text => text === "Rate 26.5"))
	})

	test(`case 10: reconciliation blank and zero Rate stay zero (${layout})`, async () => {
		for (const rate of ["", 0]) {
			const { root, props } = mountComposer("stock_reconciliation", layout, { modelValue: [groupFor(layout)] })
			await editButton(root).props.onClick()
			await tick()
			rateInputs(root).forEach(input => typeInto(input, rate))
			quantityInputs(root).forEach(input => typeInto(input, 0))
			await click(root, "Update Item")
			assert.ok(Object.values(props.modelValue[0].items[0].values).every(value => value.rate === 0 && value.qty === 0))
		}
	})

	test(`case 11: Material Receipt Rate stages (${layout})`, async () => {
		const { root, props } = mountComposer("stock_entry", layout, { purpose: "Material Receipt" })
		await fetchItem(root)
		assert.equal(rateInputs(root).length, keysFor(layout).length)
		rateInputs(root).forEach(input => typeInto(input, 35.75))
		await enterQuantities(root)
		await click(root, "OK · Add Item")
		assert.ok(Object.values(props.modelValue[0].items[0].values).every(value => value.rate === 35.75))
	})

	test(`case 12: other stock builders have no Rate input (${layout})`, async () => {
		for (const [operation, purpose] of [["stock_entry", "Material Issue"], ["stock_entry", "Material Consumed"], ["stock_entry", "Send to Warehouse"], ["stock_entry", "Receive at Warehouse"], ["stock_update", ""], ["lot_transfer", ""]]) {
			const { root } = mountComposer(operation, layout, { purpose })
			await fetchItem(root)
			assert.equal(quantityInputs(root).length, keysFor(layout).length)
			assert.equal(rateInputs(root).length, 0, `${operation} ${purpose}`)
		}
	})

	test(`case 13: rowPreparer valuation shown on Add and Update (${layout})`, async () => {
		let rate = 42.75
		let calls = 0
		const { root, props } = mountComposer("stock_update", layout, { rowPreparer: async row => {
			calls += 1
			return stockItemComposer.applyStockUpdateRates(row, Object.fromEntries(Object.keys(row.values).map(key => [key, rate])))
		} })
		await fetchItem(root)
		await enterQuantities(root)
		await click(root, "OK · Add Item")
		assert.ok(priceTexts(root).every(text => text === "Valuation Rate 42.75"))
		rate = 53.5
		await editButton(root).props.onClick()
		await tick()
		await click(root, "Update Item")
		assert.equal(calls, 2)
		assert.ok(Object.values(props.modelValue[0].items[0].values).every(value => value.rate === 53.5))
		assert.deepEqual(priceTexts(root), keysFor(layout).map(() => "Valuation Rate 53.5"))
	})
}

test("case 13: rate preparer preserves row fields and defaults missing rates to zero", () => {
	const row = groupFor("grid").items[0]
	const original = structuredClone(row)
	const prepared = stockItemComposer.applyStockUpdateRates(row, { "58 Dia": "82.125" })
	assert.deepEqual(prepared, { ...original, values: { "58 Dia": { qty: 2, rate: 82.125 }, "60 Dia": { qty: 3, rate: 0 } } })
	assert.deepEqual(row, original)
})

test("case 13: Stock Update API sends Desk rate lookup arguments", async () => {
	const previousWindow = globalThis.window
	const previousFetch = globalThis.fetch
	globalThis.window = {}
	const calls = []
	globalThis.fetch = async (url, options) => {
		calls.push({ url, args: JSON.parse(options.body) })
		return { ok: true, status: 200, json: async () => ({ message: { "58 Dia": 92.5 } }) }
	}
	try {
		const row = groupFor("grid").items[0]
		assert.deepEqual(await getStockUpdateRates(row, "Stores"), { "58 Dia": 92.5 })
		assert.deepEqual(calls[0], {
			url: "/api/method/yrp.yrp_stock.doctype.yrp_stock_update.yrp_stock_update.get_stock_update_rates",
			args: { item: "Fabric A", attributes: {}, primary_attribute: "Dia", value_keys: ["58 Dia", "60 Dia"], warehouse: "Stores", dimensions: { lot: "LOT-1" } },
		})
		await getStockUpdateRates({ name: "Plain", values: { default: { qty: 1 } } }, "Stores")
		assert.deepEqual(calls[1].args, { item: "Plain", attributes: {}, primary_attribute: "", value_keys: ["default"], warehouse: "Stores", dimensions: {} })
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})

const ComposerProbe = Vue.defineComponent({
	props: ["rowPreparer", "warehouse", "modelValue"],
	setup: (props) => () => Vue.h("composer-probe", { rowPreparer: props.rowPreparer, warehouse: props.warehouse, modelValue: props.modelValue }),
})
const probe = (root) => findNodes(root, node => node.type === "composer-probe")[0]

test("case 13: fabric dialog prepares rates only for Stock Update with warehouse", async () => {
	const calls = []
	const component = loadComponent(resolve(rootPath, "frontend/src/departments/fabric-store/FabricStockOperationDialog.vue"), {
		...modules,
		"primevue/dialog": Container, "primevue/skeleton": Control,
		"../../config/fields/stock-entry.js": { linkSearchHandlers: {} },
		"../../api/frappe.js": { getCount: async () => 1 },
		"../../api/fabricStore.js": { getStockUpdateRates: async (row, warehouse) => { calls.push(warehouse); return { default: 68.5 } } },
		"../../components/common/FormField.vue": Control,
		"../../components/documents/DocumentErrorDialog.vue": Control,
		"../../components/documents/DocumentDeleteButton.vue": () => null,
		"../../components/documents/DocumentSaveButton.vue": Control,
		"../../components/stock/StockItemComposer.vue": ComposerProbe,
		"../../utils/fieldErrors.js": fieldErrors,
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => () => {} },
		"./stockHeaderFields.js": stockHeaderFields,
	})
	for (const [operation, warehouse] of [["stock_update", "Stores"], ["stock_entry", "Stores"], ["stock_entry", ""]]) {
		const root = mountComponent(component, { visible: true, operation, initialEditor: { defaults: { warehouse }, dimensions: [] } })
		await tick()
		const row = groupFor("single").items[0]
		const prepared = await probe(root).props.rowPreparer(row)
		assert.equal(prepared.values.default.rate, operation === "stock_update" ? 68.5 : row.values.default.rate)
	}
	const root = mountComponent(component, { visible: true, operation: "stock_update", initialEditor: { defaults: { warehouse: "" }, dimensions: [] } })
	await tick()
	await assert.rejects(probe(root).props.rowPreparer(groupFor("single").items[0]), /Set Warehouse/)
	assert.deepEqual(calls, ["Stores"])
})

test("Stock Update staged Valuation Rates refresh when the Warehouse changes", async () => {
	const calls = []
	const component = loadComponent(resolve(rootPath, "frontend/src/departments/fabric-store/FabricStockOperationDialog.vue"), {
		...modules,
		"primevue/dialog": Container, "primevue/skeleton": Control,
		"../../config/fields/stock-entry.js": { linkSearchHandlers: {} },
		"../../api/frappe.js": { getCount: async () => 1 },
		"../../api/fabricStore.js": { getStockUpdateRates: async (row, warehouse) => { calls.push(warehouse); return { default: warehouse === "Annex" ? 77 : 68.5 } } },
		"../../components/common/FormField.vue": Control,
		"../../components/documents/DocumentErrorDialog.vue": Control,
		"../../components/documents/DocumentDeleteButton.vue": () => null,
		"../../components/documents/DocumentSaveButton.vue": Control,
		"../../components/stock/StockItemComposer.vue": ComposerProbe,
		"../../utils/fieldErrors.js": fieldErrors,
		"../../utils/useActionConfirmation.js": { useActionConfirmation: () => () => {} },
		"./stockHeaderFields.js": stockHeaderFields,
	})
	const root = mountComponent(component, { visible: true, operation: "stock_update", initialEditor: { defaults: { warehouse: "Stores", update_type: "Add" }, update_type_options: ["Add", "Reduce"], dimensions: [], item_groups: [groupFor("single")] } })
	await tick()
	const warehouseField = findNodes(root, node => node.type === "control" && node.props.field?.fieldname === "warehouse")[0]
	warehouseField.props["onUpdate:modelValue"]("Annex")
	await tick()
	await tick()
	assert.deepEqual(calls, ["Annex"])
	assert.equal(probe(root).props.modelValue[0].items[0].values.default.rate, 77)
})

test("case 13: cutting wrapper prepares rates only for Stock Update with warehouse", async () => {
	const calls = []
	const component = loadComponent(resolve(rootPath, "frontend/src/departments/cutting/StockItemComposer.vue"), {
		...modules,
		"../../components/stock/StockItemComposer.vue": ComposerProbe,
		"./cpmApi.js": {},
		"../../api/fabricStore.js": { getStockUpdateRates: async (row, warehouse) => { calls.push(warehouse); return { default: 71.25 } } },
	})
	for (const [operation, warehouse] of [["stock_update", "Cutting Stores"], ["lot_transfer", "Cutting Stores"]]) {
		const root = mountComponent(component, { operation, warehouse, cuttingPlan: "CP-1", editor: {} })
		const row = groupFor("single").items[0]
		const prepared = await probe(root).props.rowPreparer(row)
		assert.equal(prepared.values.default.rate, operation === "stock_update" ? 71.25 : row.values.default.rate)
	}
	const root = mountComponent(component, { operation: "stock_update", warehouse: "", cuttingPlan: "CP-1", editor: {} })
	await assert.rejects(probe(root).props.rowPreparer(groupFor("single").items[0]), /Set Warehouse/)
	assert.deepEqual(calls, ["Cutting Stores"])
})

test("case 13: cutting dialog passes source warehouse to composer", async () => {
	const component = loadComponent(resolve(rootPath, "frontend/src/departments/cutting/CpmStockOperationDialog.vue"), {
		"primevue/button": Button, "primevue/dialog": Container, "primevue/select": Control, "primevue/skeleton": Control,
		"../../components/common/LinkField.vue": LinkField,
		"../../components/documents/DocumentErrorDialog.vue": Control,
		"../../components/documents/DocumentSaveButton.vue": Control,
		"./StockItemComposer.vue": ComposerProbe,
		"../../api/fabricStore.js": {},
		"./cpmApi.js": { getStockOperationEditor: async () => ({ context: { source_warehouse: "Cutting Source" } }) },
	})
	const props = Vue.reactive({ visible: false, cuttingPlan: "CP-1", operation: "stock_update" })
	const root = mountComponent(component, props)
	props.visible = true
	await tick()
	assert.equal(probe(root).props.warehouse, "Cutting Source")
})
