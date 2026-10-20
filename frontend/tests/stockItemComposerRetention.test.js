import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const Button = (props) => Vue.h("button", props, props.label)
const LinkField = (props) => Vue.h("link-field", props)
const Message = (props, { slots }) => Vue.h("message", props, slots.default?.())
const schema = { item: "Fabric A", primary_attribute: "Dia", primary_attribute_values: ["58 Dia"], attributes: ["Colour", "Dia"], attribute_values: { Colour: ["Cream", "Red"] }, default_uom: "Kg" }
const editor = { dimensions: [{ fieldname: "lot", label: "Lot", options: "SD YRP Lot", mandatory: 1 }, { fieldname: "received_type", label: "Received Type", options: "YRP Received Type", mandatory: 1 }], permissions: {} }

function mountComposer(operation) {
	const component = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemComposer.vue"), {
		"primevue/button": Button, "primevue/message": Message, "../../components/common/LinkField.vue": LinkField,
		"../../utils/stockItemComposer.js": stockItemComposer,
	})
	const lines = []
	const props = Vue.reactive({ operation, editor, modelValue: [], schemaLoader: async () => structuredClone(schema), "onUpdate:modelValue": (value) => { props.modelValue = value; lines.push(value) } })
	return { root: mountComponent(component, props), props }
}
const links = (root) => findNodes(root, node => node.type === "link-field")
const link = (root, label) => links(root).find(node => node.props.label === label)
const linkValue = (root, label) => link(root, label).props.modelValue ?? link(root, label).props["model-value"]
const button = (root, label) => findNodes(root, node => node.type === "button" && node.props.label === label)[0]
const quantityInput = (root) => findNodes(root, node => node.type === "input" && node.props.type === "number")[0]
const setLink = async (root, label, value) => { link(root, label).props["onUpdate:modelValue"](value); await tick() }

async function addLine(root, colour, qty) {
	await setLink(root, "Colour *", colour)
	typeInto(quantityInput(root), qty)
	await tick()
	button(root, "OK · Add Item").props.onClick()
	await tick()
}

for (const operation of ["stock_update", "stock_entry", "lot_transfer", "stock_reconciliation"]) test(`${operation} item builder keeps lot, received type and item after Add and resets only quantities`, async () => {
	const { root, props } = mountComposer(operation)
	await setLink(root, "Lot *", "LOT-1")
	await setLink(root, "Received Type *", "Accepted")
	await setLink(root, "Item *", "Fabric A")
	button(root, "Get Item").props.onClick()
	await tick()
	await addLine(root, "Cream", 5)

	assert.equal(linkValue(root, "Lot *"), "LOT-1")
	assert.equal(linkValue(root, "Received Type *"), "Accepted")
	assert.equal(linkValue(root, "Item *"), "Fabric A")
	assert.equal(button(root, "Get Item").props.disabled, false)
	assert.ok(button(root, "OK · Add Item"), "attribute section stays open for the next line")
	assert.notEqual(Number(quantityInput(root).props.value ?? 0), 5)

	await addLine(root, "Red", 7)
	const rows = props.modelValue.flatMap(group => group.items)
	assert.deepEqual(rows.map(row => [row.dimensions.lot, row.dimensions.received_type, row.attributes.Colour, row.values["58 Dia"].qty]), [["LOT-1", "Accepted", "Cream", 5], ["LOT-1", "Accepted", "Red", 7]])
})
