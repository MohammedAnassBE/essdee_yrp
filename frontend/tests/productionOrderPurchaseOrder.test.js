import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as purchaseOrderSource from "../src/departments/sales/productionOrderPurchaseOrder.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

function mountDialog(props) {
	const events = { visible: [], changed: [] }
	const component = loadComponent(new URL("../src/departments/sales/ProductionOrderPurchaseOrderDialog.vue", import.meta.url).pathname, {
		"primevue/dialog": (dialogProps, { slots }) => Vue.h("dialog", dialogProps, slots.default?.()),
		"../fabric-store/PurchaseOrderEditor.vue": (editorProps) => Vue.h("purchase-order-editor", editorProps),
		"../FabricPurchaseOrder.vue": (pageProps) => Vue.h("purchase-order-page", pageProps),
		"./productionOrderPurchaseOrder.js": purchaseOrderSource,
	})
	const root = mountComponent(component, {
		visible: true,
		...props,
		"onUpdate:visible": (value) => events.visible.push(value),
		onChanged: (payload) => events.changed.push(payload),
	})
	const find = (type) => () => findNodes(root, (node) => node.type === type)[0]
	return { root, events, editor: find("purchase-order-editor"), page: find("purchase-order-page"), dialog: find("dialog") }
}
const tick = () => Vue.nextTick()

test("source lists the Production Orders the new Purchase Order is raised against", () => {
	assert.deepEqual(purchaseOrderSource.purchaseOrderSourceFor(["PPO-1"]), { production_orders: ["PPO-1"] })
	assert.deepEqual(purchaseOrderSource.purchaseOrderSourceFor(["PPO-1", "", "PPO-2"]), { production_orders: ["PPO-1", "PPO-2"] })
	assert.deepEqual(purchaseOrderSource.purchaseOrderSourceFor([]), {})
})

test("Create PO opens the editor prefilled from the Production Order", () => {
	const { dialog, editor, page } = mountDialog({ productionOrder: "PPO-1" })
	assert.equal(dialog().props.header, "New Purchase Order · PPO-1")
	assert.equal(dialog().props.closable, false)
	assert.equal(editor().props.name, "")
	assert.deepEqual(editor().props.source, { production_orders: ["PPO-1"] })
	assert.equal(page(), undefined)
})

test("Create PO from several selected Production Orders opens one editor for all of them", () => {
	const { dialog, editor } = mountDialog({ productionOrders: ["PPO-1", "PPO-2"] })
	assert.equal(dialog().props.header, "New Purchase Order · PPO-1, PPO-2")
	assert.deepEqual(editor().props.source, { production_orders: ["PPO-1", "PPO-2"] })
})

test("saving stays in the pop-up and shows the saved Purchase Order embedded", async () => {
	const state = mountDialog({ productionOrder: "PPO-1" })
	state.editor().props.onSaved({ name: "PO-NEW" })
	await tick()
	assert.deepEqual(state.events.visible, [])
	assert.deepEqual(state.events.changed, [{ name: "PO-NEW" }])
	assert.equal(state.editor(), undefined)
	assert.equal(state.page().props.presentation, "embedded")
	assert.equal(state.page().props.name, "PO-NEW")
	assert.equal(state.dialog().props.header, "Purchase Order · PO-NEW · PPO-1")
})

test("cancelling a new Purchase Order closes without saving", () => {
	const state = mountDialog({ productionOrder: "PPO-1" })
	state.editor().props.onCancel()
	assert.deepEqual(state.events.visible, [false])
	assert.deepEqual(state.events.changed, [])
})

test("a side-rail Purchase Order opens embedded; edit, actions, amendment and close stay in the pop-up", async () => {
	const state = mountDialog({ productionOrder: "PPO-1", purchaseOrder: "PO-1" })
	assert.equal(state.editor(), undefined)
	assert.equal(state.page().props.name, "PO-1")
	state.page().props.onChanged({ record: { name: "PO-1" } })
	assert.deepEqual(state.events.changed, [{ record: { name: "PO-1" } }])
	state.page().props.onEdit("PO-1")
	await tick()
	assert.equal(state.editor().props.name, "PO-1")
	assert.deepEqual(state.editor().props.source, {})
	state.editor().props.onCancel()
	await tick()
	assert.equal(state.page().props.name, "PO-1")
	state.page().props.onOpen("PO-1-1")
	await tick()
	assert.equal(state.page().props.name, "PO-1-1")
	assert.deepEqual(state.events.visible, [])
	state.page().props.onClosed()
	assert.deepEqual(state.events.visible, [false])
})

test("hidden pop-up or missing Production Order renders nothing", () => {
	const hidden = mountDialog({ visible: false, productionOrder: "PPO-1" })
	assert.equal(hidden.editor(), undefined)
	assert.equal(hidden.page(), undefined)
	assert.equal(mountDialog({ productionOrder: "" }).editor(), undefined)
})

test("Create PO is driven by the server capability and refreshes the page in the background", () => {
	const page = source("../src/departments/sales/ProductionOrder.vue")
	assert.match(page, /const priority = \[[^\]]*"create_purchase_order"/)
	assert.match(page, /<ProductionOrderPurchaseOrderDialog v-model:visible="purchaseOrderVisible" :production-order="workspace\.record\?\.name \|\| ''" :purchase-order="selectedPurchaseOrder" @changed="purchaseOrderChanged" \/>/)
	assert.match(page, /function purchaseOrderChanged\(\) \{ load\(true\) \}/)
	assert.match(page, /if \(command === "create_purchase_order"\) return openPurchaseOrder\(\)/)
	assert.match(page, /<button v-for="order in workspace\.purchase_orders"[^>]*@click="openPurchaseOrder\(order\.name\)"/)
	assert.match(page, /workspace\.purchase_orders/)
	const workspace = source("../../essdee_yrp/sales/web_workspace.py")
	assert.match(workspace, /actions\["create_purchase_order"\] = _action\(\s*can_create_purchase_order_against\(doc\)/)
})

test("Production Orders table renders read-only links with Item Name and no Against column", () => {
	const component = loadComponent(new URL("../src/departments/fabric-store/PurchaseOrderProductionOrders.vue", import.meta.url).pathname, {
		"../../components/common/DocumentLink.vue": (linkProps) => Vue.h("document-link", linkProps),
	})
	const root = mountComponent(component, { rows: [{ production_order: "PPO-1", item_name: "VEST" }, { production_order: "PPO-2", item_name: "SET" }] })
	const headers = findNodes(root, (node) => node.type === "th").map((node) => node.text)
	assert.deepEqual(headers, ["Production Order", "Item Name"])
	const links = findNodes(root, (node) => node.type === "document-link")
	assert.deepEqual(links.map((link) => [link.props.doctype, link.props.name]), [["YRP Production Order", "PPO-1"], ["YRP Production Order", "PPO-2"]])
	assert.equal(findNodes(root, (node) => ["input", "button"].includes(node.type)).length, 0)
	assert.equal(findNodes(mountComponent(component, { rows: [] }), (node) => node.type === "table").length, 0)
})

test("editor and PO page show the Production Orders table instead of Against fields", () => {
	const editor = source("../src/departments/fabric-store/PurchaseOrderEditor.vue")
	assert.match(editor, /<PurchaseOrderProductionOrders :rows="form\.production_orders" \/>/)
	assert.match(editor, /production_orders: \[\] \}\)/)
	const page = source("../src/departments/FabricPurchaseOrder.vue")
	assert.match(page, /<PurchaseOrderProductionOrders :rows="workspace\.production_orders \|\| \[\]" \/>/)
	assert.doesNotMatch(editor, /against/)
	assert.doesNotMatch(page, /"approved_by", "against"/)
	assert.doesNotMatch(source("../src/departments/fabric-store/FabricPurchaseOrders.vue"), /against/)
})

test("PPO list selects rows and creates one Purchase Order for the selection", () => {
	const list = source("../src/departments/sales/ProductionOrders.vue")
	assert.match(list, /selectable/)
	assert.match(list, /@selection-change="selectedRows = \$event"/)
	assert.match(list, /<Button v-if="selectedNames\.length" :label="`Create Purchase Order \(\$\{selectedNames\.length\}\)`" icon="pi pi-shopping-cart" severity="secondary" outlined @click="purchaseOrderVisible = true" \/>/)
	assert.match(list, /<ProductionOrderPurchaseOrderDialog v-model:visible="purchaseOrderVisible" :production-orders="selectedNames" \/>/)
})

test("the /web Purchase Order page embeds without routing away", () => {
	const page = source("../src/departments/FabricPurchaseOrder.vue")
	assert.match(page, /<component :is="presentation === 'page' \? DepartmentPage : 'div'" v-bind="pageBindings">/)
	assert.match(page, /:presentation="presentation"/)
	assert.match(page, /if \(!isEmbedded\) usePageTitle/)
	assert.match(page, /if \(isEmbedded\) return emit\("edit", workspace\.value\.record\.name\)/)
	assert.match(page, /if \(name !== requestedId && isEmbedded\) emit\("open", name\)/)
	assert.match(page, /workspace\.value = result\n\t\temit\("changed", result\)/)
	assert.match(page, /if \(!isEmbedded && workspace\.value\.permissions\?\.can_create\) actions\.push\(\{ key: "duplicate"/)
	assert.match(page, /add\("send_approval_request", "Send Request"/)
	assert.match(page, /add\("submit", "Submit"/)
	assert.match(page, /<DocumentStatusBadge v-if="approvalMessage" :label="workspace\.approval\.live_request \? 'Approval Requested' : 'Pending Approval'" tone="warning" \/>/)
	assert.match(page, /<Message v-if="approvalMessage" severity="warn" :closable="false">\{\{ approvalMessage \}\}<\/Message>/)
	assert.match(page, /if \(!approval\?\.pending_approval\) return ""/)
})
