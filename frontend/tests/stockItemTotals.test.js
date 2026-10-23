import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockItemTotals from "../src/engine/stock/stockItemTotals.js"
import * as linkTarget from "../src/utils/linkTarget.js"
import * as displayGroups from "../src/engine/stock/groupItemsForDisplay.js"

const { getEntryTotals, getUomTotals } = stockItemTotals
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
	"../../api/frappe.js": { callMethod: async () => [] },
})
const Matrix = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemMatrix.vue"), {
	"../common/DocumentLink.vue": Control,
	"../../utils/linkTarget.js": linkTarget,
	"../../engine/stock/groupItemsForDisplay.js": displayGroups,
	"../../utils/stockItemComposer.js": stockItemComposer,
	"../../engine/stock/stockItemTotals.js": stockItemTotals,
})
const textContent = (node) => node.type === "comment" ? "" : node.text + node.children.map(textContent).join("")
const footerRows = (root) => findNodes(root, node => node.type === "tfoot").flatMap(foot => foot.children.filter(child => child.type === "tr"))
const cellTexts = (row) => row.children.filter(child => ["td", "th"].includes(child.type)).map(textContent).map(text => text.replace(/\s+/g, " ").trim())
const row = (name, uom, values) => ({ name, attributes: { Colour: name }, dimensions: {}, default_uom: uom, values })
const sizedGroup = (items) => ({ primary_attribute: "Size", primary_attribute_values: ["S", "M"], attributes: ["Colour"], items })

test("UOM totals sum each size, the grand total and amount without mixing units", () => {
	const totals = getUomTotals([
		row("Red", "Nos", { S: { qty: 0.1, rate: 10 }, M: { qty: 0.2, rate: 10, secondary_qty: 1, secondary_uom: "Kg" } }),
		row("Blue", "Nos", { S: { qty: 3, amount: 45, received_qty: 1, pending_qty: 2 } }),
		row("Grey", "Kg", { M: { qty: 5 } }),
	], ["S", "M"])
	assert.deepEqual(totals.map(bucket => [bucket.uom, bucket.values.S.qty, bucket.values.M.qty, bucket.total.qty, bucket.total.amount]), [["Nos", 3.1, 0.2, 3.3, 48], ["Kg", 0, 5, 5, 0]])
	assert.equal(totals[0].secondary_uom, "Kg")
	assert.equal(totals[0].total.secondary_qty, 1)
	assert.deepEqual([totals[0].total.received_qty, totals[0].total.pending_qty], [1, 2])
})

test("UOM totals drop secondary quantity when secondary units differ", () => {
	const [bucket] = getUomTotals([
		row("Red", "Nos", { default: { qty: 1, secondary_qty: 2, secondary_uom: "Kg" } }),
		row("Blue", "Nos", { default: { qty: 1, secondary_qty: 3, secondary_uom: "Mtr" } }),
	], ["default"])
	assert.deepEqual([bucket.total.qty, bucket.total.secondary_qty, bucket.secondary_uom], [2, 0, ""])
})

test("entry totals add typed sizes and treat blank as zero", () => {
	assert.deepEqual(getEntryTotals({ S: 1.1, M: "", L: 2.2 }, { S: 10, L: 1 }, ["S", "M", "L"]), { qty: 3.3, amount: 13.2 })
	assert.deepEqual(getEntryTotals({ S: null }, {}, ["S"]), { qty: 0, amount: 0 })
})

test("saved item matrix shows a Total footer per UOM with Amount and fulfilment", () => {
	const groups = [sizedGroup([
		row("Red", "Nos", { S: { qty: 2, rate: 5, received_qty: 1, pending_qty: 1 }, M: { qty: 3, rate: 5 } }),
		row("Blue", "Nos", { S: { qty: 4, rate: 5 }, M: { qty: 1, rate: 5 } }),
	])]
	const root = mountComponent(Matrix, { doctype: "Purchase Order", groups, showPricing: true, showFulfillment: true })
	const [footer] = footerRows(root)
	assert.deepEqual(cellTexts(footer), ["Total", "6Received 1Pending 1Amount 30", "4Received 0Pending 0Amount 20", "10Received 1Pending 1Amount 50", "Nos"])
	const mixed = mountComponent(Matrix, { doctype: "YRP Stock Entry", groups: [sizedGroup([row("Red", "Nos", { S: { qty: 1 } }), row("Grey", "Kg", { M: { qty: 2 } })])] })
	assert.deepEqual(footerRows(mixed).map(cellTexts).map(cells => [cells[0], cells.at(-2)]), [["Total · Nos", "1"], ["Total · Kg", "2"]])
	assert.equal(footerRows(mountComponent(Matrix, { groups: [sizedGroup([row("Red", "Nos", { S: { qty: 1 } })])] })).length, 0)
})

test("added items show a Total footer and the size box shows a running total", async () => {
	const schema = { item: "Shirt", primary_attribute: "Size", primary_attribute_values: ["S", "M"], attributes: ["Size"], default_uom: "Nos" }
	const props = Vue.reactive({
		operation: "purchase_order", editor: { dimensions: [] }, schemaLoader: async () => schema,
		modelValue: [sizedGroup([row("Red", "Nos", { S: { qty: 2, rate: 3 }, M: { qty: 1, rate: 3 } }), row("Blue", "Nos", { S: { qty: 5, rate: 2 } })])],
	})
	const root = mountComponent(Composer, props)
	const [footer] = footerRows(root)
	assert.deepEqual(cellTexts(footer).slice(0, 5), ["Total", "7Amount 16", "1Amount 3", "8Amount 19", "Nos"])
	findNodes(root, node => node.type === "link-field" && node.props.label === "Item *")[0].props["onUpdate:modelValue"]("Shirt")
	await tick()
	await findNodes(root, node => node.type === "button" && node.props.label === "Get Item")[0].props.onClick()
	await tick()
	const inputs = findNodes(root, node => node.type === "input" && node.props.step === "0.001")
	typeInto(inputs[0], 4)
	typeInto(inputs[1], 2.5)
	await tick()
	const runningTotal = findNodes(root, node => node.props.class === "stock-composer__entry-total")[0]
	assert.equal(textContent(runningTotal), "Total 6.5")
})
