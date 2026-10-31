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

test("source prefills Against and Against ID only for a Production Order", () => {
	assert.deepEqual(purchaseOrderSource.purchaseOrderSourceFor("PPO-1"), { against: "YRP Production Order", against_id: "PPO-1" })
	assert.deepEqual(purchaseOrderSource.purchaseOrderSourceFor(""), {})
})

test("Create PO opens the editor prefilled from the Production Order", () => {
	const { dialog, editor, page } = mountDialog({ productionOrder: "PPO-1" })
	assert.equal(dialog().props.header, "New Purchase Order · PPO-1")
	assert.equal(dialog().props.closable, false)
	assert.equal(editor().props.name, "")
	assert.deepEqual(editor().props.source, { against: "YRP Production Order", against_id: "PPO-1" })
	assert.equal(page(), undefined)
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

test("editor shows Against fields read-only and the PO page and list show them", () => {
	const editor = source("../src/departments/fabric-store/PurchaseOrderEditor.vue")
	assert.match(editor, /<template v-if="form\.against_id">/)
	assert.match(editor, /<InputText id="po-against" :model-value="form\.against" disabled fluid \/>/)
	assert.match(editor, /<InputText id="po-against-id" :model-value="form\.against_id" disabled fluid \/>/)
	assert.match(editor, /against: "", against_id: "" \}\)/)
	assert.match(source("../src/departments/FabricPurchaseOrder.vue"), /"approved_by", "against", "against_id"\]/)
	assert.match(source("../src/departments/fabric-store/FabricPurchaseOrders.vue"), /"grand_total", "against", "against_id"\]/)
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
