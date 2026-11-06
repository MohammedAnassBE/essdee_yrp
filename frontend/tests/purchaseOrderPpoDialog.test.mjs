import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as rowsModule from "../src/departments/fabric-store/purchaseOrderProductionOrders.js"

const { addProductionOrderRow, hasProductionOrderChanges, productionOrderNames, productionOrderRows, removeProductionOrderRow } = rowsModule
const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

test("PPO rows add once with the searched item, remove, and detect changes", () => {
	const original = productionOrderRows([{ production_order: "PPO-1", item_name: "VEST", name: "row-1" }, { production_order: "" }])
	assert.deepEqual(original, [{ production_order: "PPO-1", item_name: "VEST" }])
	const added = addProductionOrderRow(original, { name: "PPO-2", label: "PPO-2", description: "SET", item: "SET" })
	assert.deepEqual(added, [{ production_order: "PPO-1", item_name: "VEST" }, { production_order: "PPO-2", item_name: "SET" }])
	assert.equal(addProductionOrderRow(added, { name: "PPO-1", item: "VEST" }), added)
	assert.equal(addProductionOrderRow(added, null), added)
	assert.deepEqual(productionOrderNames(removeProductionOrderRow(added, "PPO-1")), ["PPO-2"])
	assert.equal(hasProductionOrderChanges(original, original), false)
	assert.equal(hasProductionOrderChanges(original, added), true)
	assert.equal(hasProductionOrderChanges(original, []), true)
})

function mountDialog(props) {
	const searches = []
	const component = loadComponent(new URL("../src/departments/fabric-store/PurchaseOrderProductionOrderDialog.vue", import.meta.url).pathname, {
		"primevue/button": (buttonProps) => Vue.h("button", buttonProps),
		"primevue/dialog": (dialogProps, { slots }) => Vue.h("dialog", dialogProps, [slots.default?.(), slots.footer?.()]),
		"primevue/message": (messageProps, { slots }) => Vue.h("message", messageProps, slots.default?.()),
		"../../api/frappe.js": { callRead: async (method, args) => { searches.push([method, args]); return [] } },
		"../../components/common/DocumentLink.vue": (linkProps) => Vue.h("document-link", linkProps),
		"../../components/common/LinkField.vue": (fieldProps) => Vue.h("link-field", fieldProps),
		"./purchaseOrderProductionOrders.js": rowsModule,
	})
	const events = { save: [] }
	const root = mountComponent(component, { visible: true, rows: [{ production_order: "PPO-1", item_name: "VEST" }], onSave: (names) => events.save.push(names), ...props })
	const nodes = (predicate) => findNodes(root, predicate)
	return { root, events, searches, nodes }
}

test("dialog lists PPO + Item Name rows, searches by ID or item, and saves the edited table", async () => {
	const { events, searches, nodes } = mountDialog({ canRemove: true })
	assert.deepEqual(nodes((node) => node.type === "th").map((node) => node.text), ["PPO", "Item Name", ""])
	const field = nodes((node) => node.type === "link-field")[0]
	assert.equal(field.props.doctype, "YRP Production Order")
	await field.props["search-handler"]("VEST")
	assert.deepEqual(searches, [["essdee_yrp.purchase_order_against.search_production_orders", { txt: "VEST" }]])
	const save = () => nodes((node) => node.type === "button" && node.props.label === "Save")[0]
	assert.equal(save().props.disabled, true)

	field.props.onSelect({ name: "PPO-2", row: { name: "PPO-2", item: "SET" } })
	await Vue.nextTick()
	assert.deepEqual(nodes((node) => node.type === "document-link").map((node) => node.props.name), ["PPO-1", "PPO-2"])
	assert.ok(nodes((node) => node.type === "td").some((node) => node.text === "SET"))
	nodes((node) => node.type === "button" && node.props["aria-label"] === "Remove PPO-1")[0].props.onClick()
	await Vue.nextTick()
	assert.equal(save().props.disabled, false)
	save().props.onClick()
	assert.deepEqual(events.save, [["PPO-2"]])
})

test("without removal rights saved PPOs keep no remove button but newly picked ones do", async () => {
	const { nodes } = mountDialog({ canRemove: false })
	const removeButtons = () => nodes((node) => node.type === "button" && String(node.props["aria-label"] || "").startsWith("Remove ")).map((node) => node.props["aria-label"])
	assert.deepEqual(removeButtons(), [])
	nodes((node) => node.type === "link-field")[0].props.onSelect({ name: "PPO-2", row: { name: "PPO-2", item: "SET" } })
	await Vue.nextTick()
	assert.deepEqual(removeButtons(), ["Remove PPO-2"])
})

test("dialog shows the save error", () => {
	const { nodes } = mountDialog({ error: "Production Order PPO-9 is Closed." })
	assert.equal(nodes((node) => node.type === "message")[0].children[0].text, "Production Order PPO-9 is Closed.")
})

test("PO page shows Add PPO from the server capability and saves through the command", () => {
	const page = source("../src/departments/FabricPurchaseOrder.vue")
	assert.match(page, /add\("update_production_orders", "Add PPO", "pi pi-sitemap"/)
	assert.match(page, /<PurchaseOrderProductionOrderDialog v-model:visible="productionOrderEditorVisible" :rows="workspace\.production_orders \|\| \[\]"/)
	assert.match(page, /:can-remove="Boolean\(capabilities\.update_production_orders\?\.can_remove\)"/)
	assert.match(page, /runDomainCommand\("update_production_orders", \{ production_orders: productionOrders \}\)/)
	const service = source("../../essdee_yrp/fabric_store/documents/purchase_order.py")
	assert.match(service, /"eligible": can_manage_production_orders\(doc\),\n\t\t\t"can_remove": can_remove_production_orders\(doc\),/)
})
