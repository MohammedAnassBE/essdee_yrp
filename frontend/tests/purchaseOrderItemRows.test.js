import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockItemTotals from "../src/engine/stock/stockItemTotals.js"
import * as linkTarget from "../src/utils/linkTarget.js"
import * as displayGroups from "../src/engine/stock/groupItemsForDisplay.js"

const { getEntryPrimaryValues, mergeStockItemDraft } = stockItemComposer
globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const Control = (props) => Vue.h("control", props)
const Button = (props) => Vue.h("button", props, props.label)
const Container = (props, { slots }) => Vue.h("container", props, slots.default?.())
const Composer = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemComposer.vue"), {
	"primevue/button": Button,
	"primevue/message": Container,
	"../../components/common/LinkField.vue": (props) => Vue.h("link-field", props),
	"../../utils/stockItemComposer.js": stockItemComposer,
	"../../engine/stock/stockItemTotals.js": stockItemTotals,
	"../../utils/dateFormat.js": { formatDisplayDate: (value) => value || "—" },
	"../../api/frappe.js": { callMethod: async () => [] },
})
const Matrix = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemMatrix.vue"), {
	"../common/DocumentLink.vue": Control,
	"../../utils/linkTarget.js": linkTarget,
	"../../engine/stock/groupItemsForDisplay.js": displayGroups,
	"../../utils/stockItemComposer.js": stockItemComposer,
	"../../engine/stock/stockItemTotals.js": stockItemTotals,
	"../../utils/dateFormat.js": { formatDisplayDate: (value, fallback) => value || fallback },
})
const textContent = (node) => node.type === "comment" ? "" : node.text + node.children.map(textContent).join("")
const bodyRows = (root) => findNodes(root, node => node.type === "tbody").flatMap(body => body.children.filter(child => child.type === "tr"))
const footerTotals = (root) => findNodes(root, node => node.type === "tfoot").flatMap(foot => foot.children.filter(child => child.type === "tr")).map(row => textContent(row).replace(/\s+/g, " "))

const plain = (name, attributes, qty, uom, extra = {}) => ({ name, attributes, dimensions: {}, primary_attribute: "", default_uom: uom, values: { default: { qty, rate: 10 } }, ...extra })
const plainGroup = (attributes, items) => ({ attributes, primary_attribute: "", dependent_attribute: "", primary_attribute_values: [], items })
const sized = (colour, values, extra = {}) => ({ name: "Shirt", attributes: { Colour: colour }, dimensions: {}, primary_attribute: "Size", default_uom: "Nos", values, ...extra })

function nineItemGroups() {
	return [
		plainGroup(["Type", "Size"], [
			plain("Organ Needle", { Type: "UY 128 GAS 75/11", Size: "11" }, 5, "Box"),
			plain("Organ Needle", { Type: "DC X 1 75/11 J", Size: "11" }, 6, "Box"),
			plain("Organ Needle", { Type: "DC X 1 75/11 J", Size: "11" }, 2, "Box", { schedule_date: "2026-12-01" }),
		]),
		plainGroup(["Name", "Type"], [
			plain("GROZ - Beckert Needle", { Name: "Flat Lock", Type: "UY 128 GAS 75/11" }, 7, "Pack"),
			plain("GROZ - Beckert Needle", { Name: "Over Lock", Type: "DC X 27 75/11" }, 8, "Pack"),
			plain("GROZ - Beckert Needle", { Name: "Kaja", Type: "DPx5 75/11" }, 9, "Pack"),
		]),
		{ attributes: ["Colour"], primary_attribute: "Size", dependent_attribute: "", primary_attribute_values: ["S", "M"], items: [
			sized("Red", { S: { qty: 1, rate: 2 }, M: { qty: 2, rate: 2 } }),
			sized("Blue", { S: { qty: 3, rate: 2 }, M: { qty: 0, rate: 2 } }),
			sized("Red", { S: { qty: 4, rate: 2 }, M: { qty: 0, rate: 2 } }, { delivery_location: "Other" }),
		] },
	]
}

test("Purchase Order editor and saved view show all nine item rows", () => {
	const composer = mountComponent(Composer, { operation: "purchase_order", editor: { dimensions: [] }, schemaLoader: async () => ({}), modelValue: nineItemGroups() })
	assert.equal(bodyRows(composer).length, 9)
	const view = mountComponent(Matrix, { doctype: "Purchase Order", groups: nineItemGroups(), showPricing: true })
	assert.equal(bodyRows(view).length, 9)
	assert.deepEqual(footerTotals(view), ["Total13Amount 130Box", "Total24Amount 240Pack", "Total8Amount 162Amount 410Amount 20Nos"])
	assert.deepEqual(footerTotals(composer).map(text => text.match(/^Total(\d+)/)[1]), ["13", "24", "8"])
})

test("adding GROZ needles one by one never removes an Organ needle", async () => {
	const schema = { item: "GROZ - Beckert Needle", primary_attribute: "", primary_attribute_values: [], attributes: ["Name", "Type"], default_uom: "Pack" }
	const emitted = []
	const props = Vue.reactive({
		operation: "purchase_order", editor: { dimensions: [] }, schemaLoader: async () => schema,
		modelValue: [plainGroup(["Type", "Size"], [plain("Organ Needle", { Type: "UY 128 GAS 75/11", Size: "11" }, 5, "Box"), plain("Organ Needle", { Type: "DC X 1 75/11 J", Size: "11" }, 6, "Box")])],
		"onUpdate:modelValue": (value) => { emitted.push(value); props.modelValue = value },
	})
	const root = mountComponent(Composer, props)
	const link = (label) => findNodes(root, node => node.type === "link-field" && node.props.label === label)[0]
	for (const [index, name] of ["Flat Lock", "Over Lock", "Kaja"].entries()) {
		link("Item *").props["onUpdate:modelValue"]("GROZ - Beckert Needle")
		await tick()
		await findNodes(root, node => node.type === "button" && node.props.label === "Get Item")[0].props.onClick()
		await tick()
		link("Name *").props["onUpdate:modelValue"](name)
		link("Type *").props["onUpdate:modelValue"](`T${index}`)
		await tick()
		typeInto(findNodes(root, node => node.type === "input" && node.props.step === "0.001")[0], index + 1)
		await tick()
		await findNodes(root, node => node.type === "button" && node.props.label === "OK · Add Item")[0].props.onClick()
		await tick()
		const groups = emitted.at(-1)
		assert.equal(groups.reduce((count, group) => count + group.items.length, 0), 3 + index)
		assert.equal(groups[0].items.filter(item => item.name === "Organ Needle").length, 2)
	}
	assert.equal(bodyRows(root).length, 5)
})

test("editing a row keeps a saved size the Item no longer lists", () => {
	const saved = sized("Black", { S: { qty: 200 }, XXL: { qty: 130 } })
	const draft = sized("Black", { S: { qty: 210 }, M: { qty: 0 } })
	assert.deepEqual(Object.fromEntries(Object.entries(mergeStockItemDraft(saved, draft).values).map(([key, value]) => [key, value.qty])), { S: 210, M: 0, XXL: 130 })
	assert.deepEqual(getEntryPrimaryValues(["S", "M"], mergeStockItemDraft(saved, draft)), ["S", "M", "XXL"])
	assert.deepEqual(Object.keys(mergeStockItemDraft(saved, sized("White", { S: { qty: 1 } })).values), ["S"])
	assert.deepEqual(getEntryPrimaryValues([], plain("Needle", {}, 1, "Pack")), [])
})
