import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import * as accountsViews from "../src/departments/accounts/accountsViews.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { canOpenList, getPermissionRedirect, NO_PERMISSION_PATH } from "../src/router/listPermission.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const PATH = "/finishing/work-orders"
const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const layouts = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json"))
const finishingLayout = () => {
	const workspaces = JSON.parse(layouts.find((row) => row.experience_key === "finishing").config).experience_props.workspaces
	return getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "finishing" }, config: { experience_props: { workspaces } } } })
}

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES: accountsViews.ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH }
	vm.runInNewContext(routerSource, context)
	return context.router
}

async function finishingCards(sections) {
	const page = loadComponent(resolve("frontend/src/departments/Finishing.vue"), {
		"../api/finishing.js": { getFinishingCapabilities: async () => ({ sections }) },
		"../components/DepartmentPage.vue": stub("department"),
		"../components/common/WorkspaceLauncher.vue": stub("launcher"),
		"../components/common/WorkspaceLoadError.vue": stub("error"),
	})
	const root = mountComponent(page, {})
	await tick()
	return nodes(root, "launcher")[0].props.items
}

function workOrderSection(capabilities) {
	const requests = []
	const workOrders = loadComponent(resolve("frontend/src/departments/fabric-store/FabricWorkOrders.vue"), {
		"primevue/button": stub("button"), "vue-router": { useRouter: () => ({}) },
		"../../components/common/ListView.vue": (props, { slots }) => Vue.h("list", props, slots["toolbar-actions"]?.()),
		"../../components/documents/DocumentStatusBadge.vue": stub("badge"),
		"../../router/listDocumentNavigation.js": {},
	})
	const section = loadComponent(resolve("frontend/src/departments/FabricStoreSection.vue"), {
		"primevue/message": stub("message"),
		"../api/fabricStore.js": { getFabricStoreCapabilities: () => assert.fail("Finishing must use Finishing capabilities") },
		"../api/finishing.js": { getFinishingCapabilities: async () => { requests.push("finishing"); return capabilities } },
		"../api/quality.js": { getQualityCapabilities: () => assert.fail("Finishing must not use Quality capabilities") },
		"../api/sewing.js": { getSewingWorkOrderProcesses: () => assert.fail("Finishing filters by packing, not sewing processes") },
		"../components/DepartmentPage.vue": stub("department"),
		"../components/common/ListPageSkeleton.vue": stub("skeleton"),
		"../components/common/WorkspaceLoadError.vue": stub("error"),
		"./fabric-store/FabricWorkOrders.vue": workOrders,
		"./fabric-store/FabricPurchaseOrders.vue": stub("purchase"),
		"./fabric-store/FabricReports.vue": stub("reports"),
		"./fabric-store/FabricStockTransfers.vue": stub("transfers"),
	})
	const props = { section: "work_orders", basePath: "/finishing", storeName: "Finishing", workOrderViewRouteName: "finishing-work-order" }
	return { root: mountComponent(section, props), requests }
}

test("Finishing shows the Work Orders card only when the server allows Work Order read", async () => {
	const readable = await finishingCards({ plans: { can_read: true }, work_orders: { can_read: true, can_create: false } })
	const card = readable.find((item) => item.key === "work_orders")
	assert.equal(card.label, "Work Orders")
	assert.equal(card.to, PATH)
	assert.equal(readable.at(-1).key, "work_orders")
	const hidden = await finishingCards({ plans: { can_read: true } })
	assert.ok(!hidden.some((item) => item.key === "work_orders"))
})

test("the Finishing list shows all Work Orders like Fabric Store, with Finishing capabilities", async () => {
	const { root, requests } = workOrderSection({ sections: { work_orders: { can_read: true, can_create: false } } })
	await tick()
	assert.deepEqual(requests, ["finishing"])
	assert.deepEqual(nodes(root, "list")[0].props.filters, [])
	assert.equal(nodes(root, "button").length, 0, "Create needs Work Order create permission")
	const creator = workOrderSection({ sections: { work_orders: { can_read: true, can_create: true } } })
	await tick()
	assert.equal(nodes(creator.root, "button").length, 1)
})

test("the Finishing list waits for permission and never falls back to all Work Orders", async () => {
	const { root } = workOrderSection({ sections: {} })
	await tick()
	assert.equal(nodes(root, "list").length, 0)
	assert.equal(nodes(root, "message").length, 1)
})

test("the Finishing routes open the shared Work Order list, editor and page", () => {
	const router = loadRouter()
	const list = router.resolve(PATH)
	assert.equal(list.name, "finishing-work-orders")
	assert.equal(list.matched.at(-1).components.default, router.resolve("/sewing/work-orders").matched.at(-1).components.default)
	assert.deepEqual(JSON.parse(JSON.stringify(list.matched.at(-1).props.default)), { section: "work_orders", storeName: "Finishing", basePath: "/finishing", workOrderViewRouteName: "finishing-work-order", workOrderNewRouteName: "finishing-work-order-new" })
	const view = router.resolve(`${PATH}/WO-1`)
	assert.equal(view.name, "finishing-work-order")
	assert.equal(view.matched.at(-1).components.default, router.resolve("/sewing/work-orders/WO-1").matched.at(-1).components.default)
	assert.equal(view.matched.at(-1).props.default.editRouteName, "finishing-work-order-edit")
	assert.equal(router.resolve(`${PATH}/new`).name, "finishing-work-order-new")
	assert.equal(router.resolve(`${PATH}/WO-1/edit`).name, "finishing-work-order-edit")
	assert.equal(router.resolve(`${PATH}/new`).matched.at(-1).components.default, router.resolve("/sewing/work-orders/new").matched.at(-1).components.default)
	assert.equal(webDocumentPath("YRP Work Order", "WO/1", "/web/finishing/work-orders"), "/web/finishing/work-orders/WO%2F1")
})

test("the Finishing layout and Work Order read permission gate the list", () => {
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "finishing")).work_orders, [PATH])
	const router = loadRouter()
	const locked = finishingLayout()
	assert.ok(locked.workspaces.includes("work_orders"))
	assert.ok(isWorkspaceInLayout({ key: "work_orders", to: PATH }, locked))
	assert.equal(getLockedRedirect(router.resolve(PATH), locked), undefined)
	const narrow = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "finishing" }, config: { experience_props: { workspaces: ["plans"] } } } })
	assert.deepEqual(getLockedRedirect(router.resolve(PATH), narrow), { path: LAYOUT_UNAVAILABLE_PATH, query: { from: PATH }, replace: true })
	assert.equal(canOpenList(PATH, { user: { name: "finisher@example.com", can_read: ["YRP Work Order"] } }), true)
	assert.deepEqual(getPermissionRedirect({ path: PATH, fullPath: PATH, params: {} }, { user: { name: "finisher@example.com", can_read: [] } }), {
		path: NO_PERMISSION_PATH, query: { doctype: "YRP Work Order", from: PATH }, replace: true,
	})
})
