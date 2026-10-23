import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"

import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { departments } from "../src/departments/registry.js"
import { LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { goodsReceivedNoteSource, hasGoodsReceivedNoteSource } from "../src/departments/fabric-store/grnSource.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
const nodes = (root, type) => findNodes(root, (node) => node.type === type)

function loadRouter() {
	const routerSource = readFileSync(new URL("../src/router/index.js", import.meta.url), "utf8").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	return context.router
}

test("the GRN source matches the Work Order and Purchase Order Make GRN source context", () => {
	assert.deepEqual(goodsReceivedNoteSource("YRP Work Order", "WO-1"), { work_order: "WO-1" })
	assert.deepEqual(goodsReceivedNoteSource("YRP Work Order", "WO-1", "DC-1"), { work_order: "WO-1", delivery_challan: "DC-1" })
	assert.deepEqual(goodsReceivedNoteSource("Purchase Order", "PO-1", "DC-1"), { purchase_order: "PO-1" })
	assert.deepEqual(goodsReceivedNoteSource("YRP Work Order", ""), {})
	assert.equal(hasGoodsReceivedNoteSource({}), false)
	assert.equal(hasGoodsReceivedNoteSource({ delivery_challan: "DC-1" }), false)
	for (const key of ["work_order", "purchase_order", "against_id", "duplicate_from"]) assert.equal(hasGoodsReceivedNoteSource({ [key]: "X" }), true, key)
})

function grnPage(query = {}, params = {}) {
	const replaced = []
	const route = { query, params }
	const page = loadComponent(resolve("frontend/src/departments/FabricGoodsReceivedNote.vue"), {
		"vue-router": { useRoute: () => route, useRouter: () => ({ replace: async (target) => replaced.push(target) }) },
		"../components/DepartmentPage.vue": stub("department"),
		"../router/listDocumentNavigation.js": { preserveListNavigationState: () => ({}) },
		"./fabric-store/GoodsReceivedNoteSourcePicker.vue": stub("picker"),
		"./fabric-store/GoodsReceivedNoteWorkspace.vue": stub("workspace"),
		"./fabric-store/grnSource.js": { hasGoodsReceivedNoteSource },
	})
	return { root: mountComponent(page, {}), replaced }
}

test("a new GRN without a source asks for the Work Order and loads the Make GRN source", async () => {
	const { root, replaced } = grnPage({ tab: "x" })
	assert.equal(nodes(root, "workspace").length, 0)
	nodes(root, "picker")[0].props.onSelect({ work_order: "WO-1", delivery_challan: "DC-1" })
	await tick()
	assert.deepEqual(replaced, [{ query: { tab: "x", work_order: "WO-1", delivery_challan: "DC-1" } }])
})

test("a sourced, duplicated or saved GRN opens the workspace directly", () => {
	for (const [query, params] of [[{ work_order: "WO-1" }, {}], [{ duplicate_from: "GRN-1" }, {}], [{}, { goodsReceivedNoteId: "GRN-1" }]]) {
		const { root } = grnPage(query, params)
		assert.equal(nodes(root, "picker").length, 0)
		const workspace = nodes(root, "workspace")[0]
		assert.ok(workspace)
		if (query.work_order) assert.deepEqual(workspace.props["source-context"], { work_order: "WO-1" })
	}
})

function picker(workOrders = {}) {
	const calls = []
	const component = loadComponent(resolve("frontend/src/departments/fabric-store/GoodsReceivedNoteSourcePicker.vue"), {
		"primevue/button": stub("button"),
		"primevue/message": stub("message"),
		"primevue/select": stub("select"),
		"../../api/frappe.js": { getList: async (doctype, options) => { calls.push([doctype, options]); return [workOrders[options.filters[0][2]]].filter(Boolean) } },
		"../../components/common/LinkField.vue": stub("link"),
		"./grnSource.js": { goodsReceivedNoteSource },
	})
	const selected = []
	const root = mountComponent(component, { onSelect: (source) => selected.push(source) })
	return { root, calls, selected }
}
const links = (root) => nodes(root, "link")
const pick = async (link, value) => { link.props["onUpdate:modelValue"](value); await tick() }

test("the GRN source picker lists open submitted Work Orders and passes the chosen Delivery Challan", async () => {
	const { root, selected } = picker({ "WO-1": { name: "WO-1", is_rework: 0 } })
	assert.deepEqual(links(root)[0].props.filters, { docstatus: 1, open_status: "Open" })
	assert.equal(nodes(root, "button")[0].props.disabled, true)
	await pick(links(root)[0], "WO-1")
	const challan = links(root)[1]
	assert.equal(challan.props.doctype, "YRP Delivery Challan")
	assert.deepEqual(challan.props.filters, { work_order: "WO-1", docstatus: 1 })
	await pick(challan, "DC-1")
	nodes(root, "button")[0].props.onClick()
	assert.deepEqual(selected, [{ work_order: "WO-1", delivery_challan: "DC-1" }])
})

test("a rework Work Order needs a Delivery Challan before continuing", async () => {
	const { root } = picker({ "WO-R": { name: "WO-R", is_rework: 1 } })
	await pick(links(root)[0], "WO-R")
	assert.equal(links(root)[1].props.label, "Delivery Challan *")
	assert.equal(nodes(root, "button")[0].props.disabled, true)
	await pick(links(root)[1], "DC-9")
	assert.equal(nodes(root, "button")[0].props.disabled, false)
})

test("the GRN source picker can receive against a Purchase Order", async () => {
	const { root, selected } = picker()
	nodes(root, "select")[0].props["onUpdate:modelValue"]("Purchase Order")
	await tick()
	assert.equal(links(root)[0].props.doctype, "Purchase Order")
	assert.deepEqual(links(root)[0].props.filters, { docstatus: 1 })
	await pick(links(root)[0], "PO-1")
	assert.equal(links(root).length, 1)
	nodes(root, "button")[0].props.onClick()
	assert.deepEqual(selected, [{ purchase_order: "PO-1" }])
})

test("department GRN lists offer New GRN on editable departments only", () => {
	const router = loadRouter()
	const editable = { "/fabric-store": "fabric", "/accessory-store": "accessory", "/sewing": "sewing", "/finishing": "finishing", "/merch": "merch", "/planning": "planning" }
	for (const [basePath, prefix] of Object.entries(editable)) {
		const newRouteName = router.resolve(`${basePath}/goods-received-notes`).matched.at(-1).props.default.goodsReceivedNoteNewRouteName
		assert.equal(newRouteName, `${prefix}-goods-received-note-new`, basePath)
		assert.equal(router.resolve(`${basePath}/goods-received-notes/new`).name, newRouteName)
	}
	assert.equal(router.resolve("/quality/goods-received-notes").matched.at(-1).props.default.goodsReceivedNoteNewRouteName, "")
})

test("the department GRN section passes its new route to the list", async () => {
	const section = loadComponent(resolve("frontend/src/departments/FabricStoreSection.vue"), {
		"primevue/message": stub("message"),
		"../api/fabricStore.js": { getFabricStoreCapabilities: async () => ({ sections: { goods_received_notes: { can_read: true, can_create: true, doctype: "YRP Goods Received Note" } } }) },
		"../api/quality.js": {}, "../api/finishing.js": {}, "../api/sewing.js": {},
		"../components/DepartmentPage.vue": stub("department"),
		"../components/common/ListPageSkeleton.vue": stub("skeleton"),
		"../components/common/WorkspaceLoadError.vue": stub("error"),
		"./fabric-store/FabricPurchaseOrders.vue": stub("purchase"),
		"./fabric-store/FabricReports.vue": stub("reports"),
		"./fabric-store/FabricStockTransfers.vue": stub("transfers"),
		"./fabric-store/FabricWorkOrders.vue": stub("work-orders"),
		"./cut-panel-store/CutPanelDocuments.vue": stub("documents"),
	})
	const root = mountComponent(section, { section: "goods_received_notes", basePath: "/merch", goodsReceivedNoteNewRouteName: "merch-goods-received-note-new" })
	await tick()
	assert.equal(nodes(root, "documents")[0].props["new-route-name"] ?? nodes(root, "documents")[0].props.newRouteName, "merch-goods-received-note-new")
})
