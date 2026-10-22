import assert from "node:assert/strict"
import test from "node:test"
import { fileURLToPath } from "node:url"
import { resolve } from "node:path"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"

const rootPath = fileURLToPath(new URL("../../", import.meta.url))
const tick = async () => { await new Promise((resolve) => setImmediate(resolve)); await Vue.nextTick() }
const calls = []
const Composer = loadComponent(resolve(rootPath, "frontend/src/components/stock/StockItemComposer.vue"), {
	"primevue/button": (props) => Vue.h("button", props, props.label),
	"primevue/message": (props, { slots }) => Vue.h("message", props, slots.default?.()),
	"../../components/common/LinkField.vue": (props) => Vue.h("link-field", props),
	"../../utils/stockItemComposer.js": stockItemComposer,
	"../../api/frappe.js": { callMethod: async (method, args) => { calls.push({ method, args }); return ["White", "White Melange"] } },
})

test("stock attribute values search the server like a Desk Link instead of listing every value", async () => {
	const schema = { item: "Fabric A", attributes: ["Dia", "Colour"], primary_attribute: "", primary_attribute_values: [], default_uom: "Kg" }
	const root = mountComponent(Composer, { operation: "stock_entry", editor: { dimensions: [] }, modelValue: [], schemaLoader: async () => schema })
	const link = (label) => findNodes(root, (node) => node.type === "link-field" && node.props.label === label)[0]
	link("Item *").props["onUpdate:modelValue"]("Fabric A")
	await tick()
	await findNodes(root, (node) => node.type === "button" && node.props.label === "Get Item")[0].props.onClick()
	await tick()
	const colour = link("Colour *")
	assert.deepEqual(await colour.props["search-handler"]("white"), [{ name: "White", label: "White" }, { name: "White Melange", label: "White Melange" }])
	assert.deepEqual(calls, [{
		method: "yrp.yrp.doctype.yrp_item.yrp_item.search_item_attribute_values",
		args: { txt: "white", attribute: "Colour", item: "Fabric A", page_len: 20 },
	}])
	assert.equal(colour.props["create-doctype"], "YRP Item Attribute Value")
	assert.deepEqual(colour.props["create-values"], { attribute_name: "Colour" })
})
