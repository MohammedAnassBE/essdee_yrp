import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import * as accountsViews from "../src/departments/accounts/accountsViews.js"
import * as storeWorkspaces from "../src/departments/fabric-store/storeWorkspaces.js"
import { merchPurchaseLauncherItems } from "../src/departments/merch-purchase/merchPurchaseViews.js"
import { MERCH_ROUTES, merchLauncherItems } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES, PLANNING_WORKSPACES, visiblePlanningWorkspaces } from "../src/departments/planning/planningViews.js"
import { PURCHASE_REPORT_KEYS, PURCHASE_ROUTES, PURCHASE_STORE_WORKSPACE_KEYS, purchaseLauncherItems } from "../src/departments/purchase/purchaseViews.js"
import { departments } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const layouts = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json"))
const DOCUMENT_KEYS = ["delivery_challans", "goods_received_notes"]
const READABLE = { work_orders: { can_read: true }, delivery_challans: { can_read: true, doctype: "YRP Delivery Challan" }, goods_received_notes: { can_read: true, doctype: "YRP Goods Received Note" } }
/** Departments with a Work Orders card, their route prefix and the layout experience key. */
const DEPARTMENTS = {
	"/fabric-store": { experience: "fabric-store", prefix: "fabric" },
	"/accessory-store": { experience: "accessory-store", prefix: "accessory" },
	"/sewing": { experience: "sewing", prefix: "sewing" },
	"/finishing": { experience: "finishing", prefix: "finishing" },
	"/quality": { experience: "quality", prefix: "quality" },
	"/merch": { experience: "merch", prefix: "merch" },
	"/planning": { experience: "planning", prefix: "planning" },
}

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES: accountsViews.ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	return context.router
}

const launcherModules = (extra) => ({
	"../components/DepartmentPage.vue": stub("department"),
	"../components/common/WorkspaceLauncher.vue": stub("launcher"),
	"../components/common/WorkspaceLoadError.vue": stub("error"),
	"./fabric-store/storeWorkspaces.js": storeWorkspaces,
	...extra,
})

async function launcherItems(path, modules, props = {}) {
	const root = mountComponent(loadComponent(resolve(path), launcherModules(modules)), props)
	await tick()
	return nodes(root, "launcher")[0].props.items
}

function assertDocumentCards(items, basePath) {
	const cards = items.filter((item) => DOCUMENT_KEYS.includes(item.key))
	assert.deepEqual(cards.map((item) => item.label), ["Delivery Challans", "Goods Received Notes"], basePath)
	assert.deepEqual(cards.map((item) => item.to?.path || item.to), [`${basePath}/delivery-challans`, `${basePath}/goods-received-notes`], basePath)
	const workOrders = items.findIndex((item) => item.key === "work_orders")
	assert.deepEqual(items.slice(workOrders + 1, workOrders + 3).map((item) => item.key), DOCUMENT_KEYS, `${basePath} groups the cards after Work Orders`)
}

const fabricCapabilities = (sections) => ({ "../api/fabricStore.js": { getFabricStoreCapabilities: async () => ({ sections }) }, "../api/cutPanelStore.js": { getCutPanelStoreCapabilities: async () => ({ sections: {} }) } })

test("Fabric and Accessory Store launchers show Delivery Challan and GRN cards after Work Orders", async () => {
	assertDocumentCards(await launcherItems("frontend/src/departments/FabricStore.vue", fabricCapabilities(READABLE)), "/fabric-store")
	assertDocumentCards(await launcherItems("frontend/src/departments/FabricStore.vue", fabricCapabilities(READABLE), { storeName: "Accessory Store", basePath: "/accessory-store", workspaceKeys: storeWorkspaces.ACCESSORY_STORE_WORKSPACE_KEYS }), "/accessory-store")
})

test("store document cards follow Delivery Challan and GRN read permission", async () => {
	const items = await launcherItems("frontend/src/departments/FabricStore.vue", fabricCapabilities({ work_orders: READABLE.work_orders, goods_received_notes: READABLE.goods_received_notes }))
	assert.deepEqual(items.filter((item) => DOCUMENT_KEYS.includes(item.key)).map((item) => item.key), ["goods_received_notes"])
})

test("the Purchase launcher shows the Fabric Store GRN card, gated on GRN read permission", async () => {
	const purchase = (sections) => launcherItems("frontend/src/departments/FabricStore.vue", fabricCapabilities(sections), {
		storeName: "Purchase", basePath: "/purchase", workspaceKeys: PURCHASE_STORE_WORKSPACE_KEYS, reportKeys: PURCHASE_REPORT_KEYS, extraWorkspaces: purchaseLauncherItems(),
	})
	const fabricCard = storeWorkspaces.storeWorkspaces("/fabric-store").find((item) => item.key === "goods_received_notes")
	const card = (await purchase(READABLE)).filter((item) => DOCUMENT_KEYS.includes(item.key))
	assert.deepEqual(card, [{ ...fabricCard, to: "/purchase/goods-received-notes" }])
	assert.ok(!(await purchase({ delivery_challans: READABLE.delivery_challans })).some((item) => DOCUMENT_KEYS.includes(item.key)))
})

test("Purchase routes its GRN list, page and editors inside Purchase", () => {
	const router = loadRouter()
	const list = router.resolve("/purchase/goods-received-notes")
	assert.equal(list.name, "purchase-goods-received-notes")
	const { section, basePath, goodsReceivedNoteViewRouteName, goodsReceivedNoteNewRouteName } = list.matched.at(-1).props.default
	assert.deepEqual([section, basePath, goodsReceivedNoteViewRouteName, goodsReceivedNoteNewRouteName], ["goods_received_notes", "/purchase", "purchase-goods-received-note", "purchase-goods-received-note-new"])
	const fabricPage = router.resolve("/fabric-store/goods-received-notes/GRN-1").matched.at(-1).components.default
	const view = router.resolve("/purchase/goods-received-notes/GRN-1")
	assert.equal(view.name, "purchase-goods-received-note")
	assert.equal(view.matched.at(-1).components.default, fabricPage)
	assert.equal(view.matched.at(-1).props.default.backTo, "/purchase/goods-received-notes")
	assert.equal(router.resolve("/purchase/goods-received-notes/new").name, "purchase-goods-received-note-new")
	assert.equal(router.resolve("/purchase/goods-received-notes/GRN-1/edit").name, "purchase-goods-received-note-edit")
	assert.ok(!router.getRoutes().some((route) => route.path.startsWith("/purchase/delivery-challans")))
	assert.equal(webDocumentPath("YRP Goods Received Note", "GRN/1", "/web/purchase/goods-received-notes"), "/web/purchase/goods-received-notes/GRN%2F1")
})

test("the Purchase layout lists the GRN card and opens its list", () => {
	const router = loadRouter()
	const workspaces = JSON.parse(layouts.find((layout) => layout.experience_key === "purchase").config).experience_props.workspaces
	assert.ok(workspaces.includes("goods_received_notes"))
	const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "purchase" }, config: { experience_props: { workspaces } } } })
	assert.ok(isWorkspaceInLayout({ to: "/purchase/goods-received-notes" }, locked))
	for (const path of ["/purchase/goods-received-notes", "/purchase/goods-received-notes/new"]) assert.equal(getLockedRedirect(router.resolve(path), locked), undefined, path)
})

test("the Planning launcher shows the Finishing Plan Dispatch card, gated on its read permission", () => {
	const card = (sections) => visiblePlanningWorkspaces(sections).filter((item) => item.key === "dispatches")
	const finishing = source("../src/departments/Finishing.vue").match(/\{ key: "dispatches"[^}]*\}/)[0]
	const [planning] = card({ dispatches: { can_read: true } })
	for (const field of ["label", "description", "icon"]) assert.ok(finishing.includes(`${field}: "${planning[field]}"`), field)
	assert.equal(planning.to, "/planning/dispatches")
	assert.deepEqual(card({ dispatches: { can_read: false } }), [])
})

test("Planning routes the Finishing Plan Dispatch list and pages inside Planning", async () => {
	const router = loadRouter()
	const finishing = router.resolve("/finishing/dispatches/FPD-1").matched.at(-1).components.default
	const props = { basePath: "/planning", backLabel: "Planning", viewRouteName: "planning-dispatch" }
	for (const [path, name] of [["/planning/dispatches", "planning-dispatches"], ["/planning/dispatches/new", "planning-dispatch-new"], ["/planning/dispatches/FPD-1", "planning-dispatch"]]) {
		const route = router.resolve(path)
		assert.equal(route.name, name)
		assert.deepEqual({ ...route.matched.at(-1).props.default }, props)
	}
	assert.equal(router.resolve("/planning/dispatches/FPD-1").matched.at(-1).components.default, finishing)
	assert.equal(webDocumentPath("SD YRP Finishing Plan Dispatch", "FPD/1", "/web/planning/dispatches"), "/web/planning/dispatches/FPD%2F1")

	const navigations = []
	const pushes = []
	const list = loadComponent(resolve("frontend/src/departments/finishing/FinishingDispatches.vue"), {
		"primevue/button": stub("button"),
		"vue-router": { useRouter: () => ({ push: (target) => pushes.push(target) }) },
		"../../api/finishing.js": { getFinishingCapabilities: async () => ({ sections: { dispatches: { can_read: true, can_create: true } } }) },
		"../../components/DepartmentPage.vue": stub("department"),
		"../../components/common/ListView.vue": (listProps, { slots }) => Vue.h("list", listProps, slots["toolbar-actions"]?.()),
		"../../components/common/WorkspaceLoadError.vue": stub("error"),
		"../../router/listDocumentNavigation.js": { openListDocument: (_router, row, _snapshot, options) => navigations.push({ name: options.routeName, params: { [options.paramName]: row.name } }) },
	})
	const root = mountComponent(list, props)
	await tick()
	assert.equal(nodes(root, "department")[0].props["back-to"], "/planning")
	nodes(root, "list")[0].props.onRowClick({ name: "FPD-1" })
	assert.deepEqual(navigations, [{ name: "planning-dispatch", params: { dispatchId: "FPD-1" } }])
	nodes(root, "button")[0].props.onClick()
	assert.deepEqual(pushes, ["/planning/dispatches/new"])
})

test("the Planning layout lists the Finishing Plan Dispatch card and opens its pages", () => {
	const router = loadRouter()
	const workspaces = JSON.parse(layouts.find((layout) => layout.experience_key === "planning").config).experience_props.workspaces
	assert.ok(workspaces.includes("dispatches"))
	const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "planning" }, config: { experience_props: { workspaces } } } })
	assert.ok(isWorkspaceInLayout({ to: "/planning/dispatches" }, locked))
	for (const path of ["/planning/dispatches", "/planning/dispatches/new"]) assert.equal(getLockedRedirect(router.resolve(path), locked), undefined, path)
})

test("Finishing and Quality launchers show the document cards only when readable", async () => {
	const finishing = (sections) => launcherItems("frontend/src/departments/Finishing.vue", { "../api/finishing.js": { getFinishingCapabilities: async () => ({ sections }) } })
	const quality = (sections) => launcherItems("frontend/src/departments/Quality.vue", { "../api/quality.js": { getQualityCapabilities: async () => ({ sections }) } })
	assertDocumentCards(await finishing(READABLE), "/finishing")
	assertDocumentCards(await quality(READABLE), "/quality")
	assert.ok(!(await finishing({ work_orders: { can_read: true } })).some((item) => DOCUMENT_KEYS.includes(item.key)))
})

test("the Sewing launcher keeps the selected unit on the document cards", async () => {
	const shell = (props, { slots }) => Vue.h("shell", props, slots.default?.({ capabilities: { sections: READABLE }, supplier: "Unit 1" }))
	const root = mountComponent(loadComponent(resolve("frontend/src/departments/sewing/SewingLauncher.vue"), {
		"../../components/common/WorkspaceLauncher.vue": stub("launcher"),
		"./SewingBackLink.vue": stub("back"), "./SewingWorkspaceShell.vue": shell, "./SewingUnitPicker.vue": stub("picker"), "../fabric-store/storeWorkspaces.js": storeWorkspaces,
	}), {})
	await tick()
	const items = nodes(root, "launcher")[0].props.items
	assertDocumentCards(items, "/sewing")
	assert.deepEqual(items.find((item) => item.key === "delivery_challans").to.query, { supplier: "Unit 1" })
})

test("Merch, Merch & Purchase and Planning launcher items include the document cards", () => {
	assertDocumentCards(merchLauncherItems(), "/merch")
	assertDocumentCards(merchPurchaseLauncherItems(), "/merch")
	assertDocumentCards(PLANNING_WORKSPACES, "/planning")
})

test("each department routes its Delivery Challan and GRN lists, pages and editors inside the department", () => {
	const router = loadRouter()
	const cutPanelPage = router.resolve("/cut-panel-store/delivery-challans/DC-1").matched.at(-1).components.default
	for (const [basePath, { prefix }] of Object.entries(DEPARTMENTS)) {
		for (const [segment, section, param] of [["delivery-challans", "delivery_challans", "delivery-challan"], ["goods-received-notes", "goods_received_notes", "goods-received-note"]]) {
			const list = router.resolve(`${basePath}/${segment}`)
			assert.equal(list.name, `${prefix}-${segment}`, basePath)
			assert.equal(list.matched.at(-1).props.default.section, section)
			assert.equal(list.matched.at(-1).props.default.basePath ?? "/fabric-store", basePath)
			const view = router.resolve(`${basePath}/${segment}/DOC-1`)
			assert.equal(view.name, `${prefix}-${param}`, basePath)
			if (segment === "delivery-challans") assert.equal(view.matched.at(-1).components.default, cutPanelPage)
			if (basePath === "/quality") continue
			assert.equal(router.resolve(`${basePath}/${segment}/new`).name, `${prefix}-${param}-new`)
			if (segment === "delivery-challans") assert.equal(list.matched.at(-1).props.default.deliveryChallanNewRouteName, `${prefix}-${param}-new`, basePath)
			assert.equal(router.resolve(`${basePath}/${segment}/DOC-1/edit`).name, `${prefix}-${param}-edit`)
		}
	}
})

test("document pages opened inside a department stay in that department", () => {
	for (const basePath of ["/accessory-store", "/finishing", "/quality", "/merch", "/planning"]) {
		assert.equal(webDocumentPath("YRP Delivery Challan", "DC/1", `/web${basePath}/delivery-challans`), `/web${basePath}/delivery-challans/DC%2F1`)
		assert.equal(webDocumentPath("YRP Goods Received Note", "GRN/1", `/web${basePath}/goods-received-notes`), `/web${basePath}/goods-received-notes/GRN%2F1`)
	}
})

test("every Work Orders department layout lists the document cards and opens their lists", () => {
	const router = loadRouter()
	for (const [basePath, { experience }] of Object.entries(DEPARTMENTS)) {
		const row = layouts.find((layout) => layout.experience_key === experience)
		const workspaces = JSON.parse(row.config).experience_props.workspaces
		assert.ok(DOCUMENT_KEYS.every((key) => workspaces.includes(key)), experience)
		const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: experience }, config: { experience_props: { workspaces } } } })
		for (const segment of ["delivery-challans", "goods-received-notes"]) {
			assert.ok(isWorkspaceInLayout({ to: `${basePath}/${segment}` }, locked), `${experience} ${segment}`)
			assert.equal(getLockedRedirect(router.resolve(`${basePath}/${segment}`), locked), undefined)
		}
	}
	const merchPurchase = JSON.parse(layouts.find((layout) => layout.experience_key === "merch-purchase").config).experience_props.workspaces
	assert.ok(DOCUMENT_KEYS.every((key) => merchPurchase.includes(key)))
})

function documentSection(basePath, { processes = async () => ["Stitching"], capabilities = { sections: READABLE } } = {}) {
	const navigations = []
	const section = loadComponent(resolve("frontend/src/departments/FabricStoreSection.vue"), {
		"primevue/message": stub("message"),
		"primevue/button": stub("button"),
		"vue-router": { useRouter: () => ({}) },
		"../api/fabricStore.js": { getFabricStoreCapabilities: async () => capabilities },
		"../api/quality.js": { getQualityCapabilities: async () => capabilities },
		"../api/finishing.js": { getFinishingCapabilities: async () => capabilities },
		"../api/sewing.js": { getSewingWorkOrderProcesses: processes },
		"../components/DepartmentPage.vue": stub("department"),
		"../components/common/ListPageSkeleton.vue": stub("skeleton"),
		"../components/common/WorkspaceLoadError.vue": stub("error"),
		"../../components/common/ListView.vue": stub("list"),
		"../../components/documents/DocumentStatusBadge.vue": stub("badge"),
		"../../router/listDocumentNavigation.js": { openListDocument: (_router, row, _snapshot, options) => navigations.push({ name: options.routeName, params: { [options.paramName]: row.name } }) },
		"./fabric-store/FabricPurchaseOrders.vue": stub("purchase"),
		"./fabric-store/FabricReports.vue": stub("reports"),
		"./fabric-store/FabricStockTransfers.vue": stub("transfers"),
		"./fabric-store/FabricWorkOrders.vue": stub("work-orders"),
	})
	const prefix = DEPARTMENTS[basePath].prefix
	const props = { section: "delivery_challans", basePath, deliveryChallanViewRouteName: `${prefix}-delivery-challan`, goodsReceivedNoteViewRouteName: `${prefix}-goods-received-note` }
	return { root: mountComponent(section, props), navigations, props }
}

test("department Delivery Challan lists reuse the Cut Panel document list with the Work Order scope", async () => {
	const fabric = documentSection("/fabric-store")
	await tick()
	const list = nodes(fabric.root, "list")[0]
	assert.equal(list.props.doctype, "YRP Delivery Challan")
	assert.deepEqual(list.props.filters, [], "Fabric Store Work Orders are unscoped, so its Delivery Challans are too")
	assert.ok(list.props["default-columns"].includes("work_order"))
	assert.ok(!list.props["default-columns"].includes("cut_panel_movement"))
	list.props.onRowClick({ name: "DC-1" })
	assert.deepEqual(fabric.navigations, [{ name: "fabric-delivery-challan", params: { deliveryChallanId: "DC-1" } }])

	const sewing = documentSection("/sewing")
	await tick()
	assert.deepEqual(nodes(sewing.root, "list")[0].props.filters, [["process_name", "in", ["Stitching"]]])
	const quality = documentSection("/quality")
	await tick()
	assert.deepEqual(nodes(quality.root, "list")[0].props.filters, [["docstatus", "=", 1], ["process_name", "in", ["Stitching"]]])
})

test("department GRN lists open the department GRN page", async () => {
	const { root, navigations } = documentSection("/finishing", { capabilities: { sections: READABLE } })
	await tick()
	const list = nodes(root, "list")[0]
	assert.equal(list.props.doctype, "YRP Delivery Challan")
	const grn = loadComponent(resolve("frontend/src/departments/cut-panel-store/CutPanelDocuments.vue"), {
		"primevue/button": stub("button"),
		"vue-router": { useRouter: () => ({}) },
		"../../components/common/ListView.vue": stub("list"),
		"../../router/listDocumentNavigation.js": { openListDocument: (_router, row, _snapshot, options) => navigations.push({ name: options.routeName, params: { [options.paramName]: row.name } }) },
	})
	const grnRoot = mountComponent(grn, { capability: READABLE.goods_received_notes, filters: [], viewRouteName: "finishing-goods-received-note" })
	const grnList = nodes(grnRoot, "list")[0]
	assert.ok(grnList.props["default-columns"].includes("against_id"))
	grnList.props.onRowClick({ name: "GRN-1" })
	assert.deepEqual(navigations.at(-1), { name: "finishing-goods-received-note", params: { goodsReceivedNoteId: "GRN-1" } })
})

test("department document lists show a permission notice without read access", async () => {
	const { root } = documentSection("/merch", { capabilities: { sections: { work_orders: { can_read: true } } } })
	await tick()
	assert.equal(nodes(root, "list").length, 0)
	assert.equal(nodes(root, "message").length, 1)
})

test("the Cut Panel Store document lists keep their Cut Panel Movement scope", () => {
	const grn = loadComponent(resolve("frontend/src/departments/cut-panel-store/CutPanelDocuments.vue"), {
		"primevue/button": stub("button"),
		"vue-router": { useRouter: () => ({}) },
		"../../components/common/ListView.vue": stub("list"),
		"../../router/listDocumentNavigation.js": {},
	})
	const list = nodes(mountComponent(grn, { capability: READABLE.delivery_challans }), "list")[0]
	assert.deepEqual(list.props.filters, [["cut_panel_movement", "is", "set"]])
	assert.ok(list.props["default-columns"].includes("cut_panel_movement"))
})
