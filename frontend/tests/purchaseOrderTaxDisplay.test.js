import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { Vue, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockItemTotals from "../src/engine/stock/stockItemTotals.js"
import * as linkTarget from "../src/utils/linkTarget.js"
import * as displayGroups from "../src/engine/stock/groupItemsForDisplay.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const Control = (props) => Vue.h("control", props)
const Container = (props, { slots }) => Vue.h("container", props, slots.default?.())
const Composer = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemComposer.vue"), {
	"primevue/button": (props) => Vue.h("button", props, props.label),
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
const sizedGroups = () => [{ attributes: ["Colour"], primary_attribute: "Size", primary_attribute_values: ["S", "M"], items: [{ name: "Tee", attributes: { Colour: "Red" }, dimensions: {}, primary_attribute: "Size", default_uom: "Nos", values: { S: { qty: 2, rate: 10, tax: "5" }, M: { qty: 3, rate: 12, tax: "18" } } }] }]
const plainGroups = () => [{ attributes: [], primary_attribute: "", primary_attribute_values: [], items: [{ name: "Label", attributes: {}, dimensions: {}, primary_attribute: "", default_uom: "Nos", values: { default: { qty: 4, rate: 1, tax: "" } } }] }]

test("formatTaxPercent shows the tax slab percentage and a dash for untaxed rows", () => {
	assert.equal(stockItemComposer.formatTaxPercent("18"), "18%")
	assert.equal(stockItemComposer.formatTaxPercent(""), "—")
	assert.equal(stockItemComposer.formatTaxPercent(null), "—")
})

test("purchase order matrix shows each cell's tax percentage", () => {
	const text = textContent(mountComponent(Matrix, { doctype: "Purchase Order", groups: sizedGroups(), showPricing: true }))
	assert.match(text, /Tax 5%/)
	assert.match(text, /Tax 18%/)
	assert.match(textContent(mountComponent(Matrix, { doctype: "Purchase Order", groups: plainGroups(), showPricing: true })), /Tax —/)
	assert.doesNotMatch(textContent(mountComponent(Matrix, { doctype: "Purchase Order", groups: sizedGroups() })), /Tax/, "pricing-free views such as the PO pop-up stay price free")
})

test("non purchase order matrices do not show tax", () => {
	assert.doesNotMatch(textContent(mountComponent(Matrix, { doctype: "YRP Stock Entry", groups: sizedGroups() })), /Tax/)
})

test("purchase order item builder rows show each cell's tax percentage", () => {
	const props = { operation: "purchase_order", editor: { dimensions: [] }, schemaLoader: async () => ({}) }
	const sized = textContent(mountComponent(Composer, { ...props, modelValue: sizedGroups() }))
	assert.match(sized, /Tax 5%/)
	assert.match(sized, /Tax 18%/)
	assert.match(textContent(mountComponent(Composer, { ...props, modelValue: plainGroups() })), /Tax —/)
	assert.doesNotMatch(textContent(mountComponent(Composer, { ...props, operation: "stock_entry", modelValue: sizedGroups() })), /Tax \d/)
})
