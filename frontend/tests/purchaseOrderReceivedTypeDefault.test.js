import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { readFileSync } from "node:fs"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockItemTotals from "../src/engine/stock/stockItemTotals.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const Button = (props) => Vue.h("button", props, props.label)
const LinkField = (props) => Vue.h("link-field", props)
const Message = (props, { slots }) => Vue.h("message", props, slots.default?.())
const schema = { item: "Fabric A", primary_attribute: "", primary_attribute_values: [], attributes: [], attribute_values: {}, default_uom: "Kg" }
const dimensions = [{ fieldname: "lot", label: "Lot", options: "SD YRP Lot", mandatory: 1 }, { fieldname: "received_type", label: "Received Type", options: "YRP Received Type", mandatory: 1 }]

function mountComposer(modelValue = []) {
	const component = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemComposer.vue"), {
		"primevue/button": Button, "primevue/message": Message, "../../components/common/LinkField.vue": LinkField,
		"../../utils/stockItemComposer.js": stockItemComposer, "../../engine/stock/stockItemTotals.js": stockItemTotals,
		"../../api/frappe.js": { callMethod: async () => [] },
	})
	const editor = { dimensions, locked_dimensions: [], default_dimensions: { received_type: "Accepted" }, permissions: {} }
	const props = Vue.reactive({ operation: "purchase_order", editor, modelValue, schemaLoader: async () => structuredClone(schema), "onUpdate:modelValue": (value) => { props.modelValue = value } })
	return mountComponent(component, props)
}
const link = (root, label) => findNodes(root, node => node.type === "link-field").find(node => node.props.label === label)
const linkValue = (root, label) => link(root, label).props.modelValue ?? link(root, label).props["model-value"]
const button = (root, label) => findNodes(root, node => node.type === "button" && node.props.label === label)[0]
const setLink = async (root, label, value) => { link(root, label).props["onUpdate:modelValue"](value); await tick() }

test("purchase order item builder prefills Received Type from the editor default", async () => {
	const root = mountComposer()
	assert.equal(linkValue(root, "Received Type *"), "Accepted")
	await setLink(root, "Item *", "Fabric A")
	button(root, "Get Item").props.onClick()
	await tick()
	assert.equal(linkValue(root, "Received Type *"), "Accepted")
})

test("purchase order item builder keeps a user-chosen Received Type through Get Item", async () => {
	const root = mountComposer()
	await setLink(root, "Received Type *", "Rejected")
	await setLink(root, "Item *", "Fabric A")
	button(root, "Get Item").props.onClick()
	await tick()
	assert.equal(linkValue(root, "Received Type *"), "Rejected")
})

test("editing a saved purchase order row keeps its stored Received Type", async () => {
	const saved = [{ item: "Fabric A", attributes: [], primary_attribute: "", primary_attribute_values: [], items: [{ name: "Fabric A", attributes: {}, dimensions: { lot: "LOT-1", received_type: null }, default_uom: "Kg", values: { default: { qty: 2, rate: 0 } } }] }]
	const root = mountComposer(saved)
	findNodes(root, node => node.type === "button" && node.props.title === "Edit item")[0].props.onClick()
	await tick()
	assert.equal(linkValue(root, "Received Type *") ?? null, null)
})

test("purchase order editor passes the server default dimensions to the item builder", () => {
	const source = readFileSync(resolve(rootPath, "frontend/src/departments/fabric-store/PurchaseOrderEditor.vue"), "utf8")
	assert.match(source, /default_dimensions: editor\.value\.default_dimensions \|\| \{\}/)
})
