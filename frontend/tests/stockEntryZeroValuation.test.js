import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent, typeInto } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockItemTotals from "../src/engine/stock/stockItemTotals.js"

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
const textContent = (node) => node.type === "comment" ? "" : node.text + node.children.map(textContent).join("")
const button = (root, label) => findNodes(root, node => node.type === "button" && node.props.label === label)[0]
const zeroValuationBox = (root) => findNodes(root, node => node.type === "input" && node.props.type === "checkbox" && !("data-row-select" in node.props))[0]

function mountComposer(operation, purpose) {
	const props = Vue.reactive({ operation, purpose, editor: { dimensions: [] }, modelValue: [], schemaLoader: async () => structuredClone(schema), "onUpdate:modelValue": (value) => { props.modelValue = value } })
	return { root: mountComponent(Composer, props), props }
}

async function addTape(root, allowZero) {
	findNodes(root, node => node.type === "link-field" && node.props.label === "Item *")[0].props["onUpdate:modelValue"]("Tape")
	await tick()
	button(root, "Get Item").props.onClick()
	await tick()
	if (allowZero) {
		assert.match(textContent(root), /Allow zero valuation rate/)
		const box = zeroValuationBox(root)
		box.checked = true
		for (const handler of box.listeners.change || []) handler({ target: box })
	}
	typeInto(findNodes(root, node => node.type === "input" && node.props.type === "number")[0], 4)
	await tick()
	button(root, "OK · Add Item").props.onClick()
	await tick()
}

test("Material Receipt rows can allow a zero valuation rate", async () => {
	const { root, props } = mountComposer("stock_entry", "Material Receipt")
	await addTape(root, true)

	assert.equal(props.modelValue[0].items[0].allow_zero_valuation_rate, true)
})

test("every Stock Entry purpose offers a zero valuation rate per row", async () => {
	for (const purpose of ["Material Issue", "Send to Warehouse", "Receive at Warehouse", "Material Consumed"]) {
		const { root, props } = mountComposer("stock_entry", purpose)
		await addTape(root, true)
		assert.equal(props.modelValue[0].items[0].allow_zero_valuation_rate, true, purpose)
	}
})

test("other stock operations do not offer a zero valuation rate", async () => {
	const { root, props } = mountComposer("stock_update")
	await addTape(root, false)

	assert.equal(zeroValuationBox(root), undefined)
	assert.equal(props.modelValue[0].items[0].allow_zero_valuation_rate, false)
})
