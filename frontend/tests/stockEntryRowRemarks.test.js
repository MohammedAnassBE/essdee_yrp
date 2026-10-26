import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockItemTotals from "../src/engine/stock/stockItemTotals.js"
import * as linkTarget from "../src/utils/linkTarget.js"
import * as displayGroups from "../src/engine/stock/groupItemsForDisplay.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}
const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await Vue.nextTick() }
const Button = (props) => Vue.h("button", props, props.label)
const Control = (props) => Vue.h("control", props)
const schema = { item: "Tape", primary_attribute: "", primary_attribute_values: [], attributes: [], default_uom: "Nos" }
const Composer = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemComposer.vue"), {
	"primevue/button": Button, "primevue/message": Control, "../../components/common/LinkField.vue": (props) => Vue.h("link-field", props),
	"../../utils/stockItemComposer.js": stockItemComposer, "../../engine/stock/stockItemTotals.js": stockItemTotals,
	"../../utils/dateFormat.js": { formatDisplayDate: (value) => value || "—" }, "../../api/frappe.js": { callMethod: async () => [] },
})
const Matrix = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemMatrix.vue"), {
	"../common/DocumentLink.vue": Control, "../../utils/linkTarget.js": linkTarget, "../../engine/stock/groupItemsForDisplay.js": displayGroups,
	"../../utils/stockItemComposer.js": stockItemComposer, "../../engine/stock/stockItemTotals.js": stockItemTotals,
	"../../utils/dateFormat.js": { formatDisplayDate: (value, fallback) => value || fallback },
})
const textContent = (node) => node.type === "comment" ? "" : node.text + node.children.map(textContent).join("")
const button = (root, label) => findNodes(root, node => node.type === "button" && node.props.label === label)[0]
const remarksInput = (root) => findNodes(root, node => node.type === "textarea" && node.props["aria-label"] === "Row remarks")[0]
const stagedRows = (root) => findNodes(root, node => node.type === "tbody").flatMap(body => body.children.filter(child => child.type === "tr"))

function mountComposer(operation) {
	const props = Vue.reactive({ operation, editor: { dimensions: [] }, modelValue: [], schemaLoader: async () => structuredClone(schema), "onUpdate:modelValue": (value) => { props.modelValue = value } })
	return { root: mountComponent(Composer, props), props }
}

async function addTape(root, remarks) {
	findNodes(root, node => node.type === "link-field" && node.props.label === "Item *")[0].props["onUpdate:modelValue"]("Tape")
	await tick()
	button(root, "Get Item").props.onClick()
	await tick()
	if (remarks !== undefined) typeInto(remarksInput(root), remarks)
	typeInto(findNodes(root, node => node.type === "input" && node.props.type === "number")[0], 4)
	await tick()
	button(root, "OK · Add Item").props.onClick()
	await tick()
}

test("Stock Entry rows take remarks, show them on the staged row and reload them for edit", async () => {
	const { root, props } = mountComposer("stock_entry")
	await addTape(root, "Loose roll")

	assert.equal(props.modelValue[0].items[0].remarks, "Loose roll")
	assert.match(textContent(stagedRows(root)[0]), /Loose roll/)
	assert.equal(remarksInput(root).value ?? remarksInput(root).props.value ?? "", "", "next row starts without remarks")

	findNodes(root, node => node.type === "button" && node.props.title === "Edit item")[0].props.onClick()
	await tick()
	assert.equal(remarksInput(root).value ?? remarksInput(root).props.value, "Loose roll")
})

test("other stock operations do not offer row remarks", async () => {
	const { root, props } = mountComposer("stock_update")
	await addTape(root)

	assert.equal(remarksInput(root), undefined)
	assert.equal("remarks" in props.modelValue[0].items[0], false)
})

test("saved Stock Entry view shows each row's remarks", () => {
	const groups = [{ attributes: [], primary_attribute: "", items: [{ name: "Tape", dimensions: {}, attributes: {}, values: { default: { qty: 4 } }, remarks: "Loose roll" }] }]
	const view = mountComponent(Matrix, { doctype: "YRP Stock Entry", groups })
	assert.equal(textContent(view).split("Loose roll").length - 1, 1)
})
