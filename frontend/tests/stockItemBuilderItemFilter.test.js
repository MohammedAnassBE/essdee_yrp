import assert from "node:assert/strict"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as stockItemComposer from "../src/utils/stockItemComposer.js"
import * as stockItemTotals from "../src/engine/stock/stockItemTotals.js"

globalThis.Document ??= class Document {}
globalThis.ShadowRoot ??= class ShadowRoot {}

function itemFilters(editor) {
	const component = loadComponent("frontend/src/components/stock/StockItemComposer.vue", {
		"primevue/button": (props) => Vue.h("button", props),
		"primevue/message": (props) => Vue.h("message", props),
		"../../components/common/LinkField.vue": (props) => Vue.h("link-field", props),
		"../../utils/stockItemComposer.js": stockItemComposer, "../../engine/stock/stockItemTotals.js": stockItemTotals,
		"../../api/frappe.js": { callMethod: async () => [] },
	})
	const root = mountComponent(component, { operation: "stock_entry", editor, modelValue: [], schemaLoader: async () => ({}) })
	return findNodes(root, node => node.type === "link-field" && node.props.label === "Item *")[0].props.filters
}

test("builder fallback Item filters exclude variants", () => {
	assert.deepEqual(itemFilters({ dimensions: [] }), { is_stock_item: 1, disabled: 0, variant_of: ["is", "not set"] })
})

test("builder passes through server Item filters", () => {
	const filters = { disabled: 0, variant_of: ["is", "not set"], is_purchase_item: 1 }
	assert.deepEqual(itemFilters({ dimensions: [], item_filters: filters }), filters)
})
