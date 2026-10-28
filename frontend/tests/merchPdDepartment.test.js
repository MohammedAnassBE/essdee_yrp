import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"
import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"

import { merchPdLauncherItems } from "../src/departments/merch-pd/merchPdViews.js"
import { MERCH_ROUTES, visibleMerchLauncherItems } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES, pdLauncherItems } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { canOpenList, NO_PERMISSION_PATH } from "../src/router/listPermission.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const layout = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.experience_key === "merch-pd")
const workspaces = JSON.parse(layout.config).experience_props.workspaces
const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "merch-pd" }, config: { experience_props: { workspaces } } } })
const items = merchPdLauncherItems()
const notInLayout = (from) => ({ path: LAYOUT_UNAVAILABLE_PATH, query: { from }, replace: true })

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH }
	vm.runInNewContext(routerSource, context)
	return context.router
}

test("Merch PD shows Lot, Item Production Detail, Purchase Order, Vendor Bill Tracking and Lotwise Item Profit", () => {
	assert.deepEqual(items.map((item) => [item.label, item.to]), [
		["Lot", "/merch/lots"],
		["Item Production Detail", "/merch/item-production-details"],
		["Purchase Orders", "/purchase/purchase-orders"],
		["Vendor Bill Tracking", "/merch/bill-tracking"],
		["Lotwise Item Profit", "/pd/lotwise-item-profits"],
	])
	assert.deepEqual(workspaces, ["lots", "item_production_details", "purchase_orders", "bill_tracking", "lotwise_item_profits"], "the shipped layout lists every card")
	assert.equal(layout.name, "Merch PD")
	assert.equal(layout.render_mode, "Registered Experience")
	assert.deepEqual(pdLauncherItems().map((item) => item.key), ["products", "product_releases", "lotwise_item_profits", "lay_sheet_planner"])
})

test("the department combines Merch, Purchase and PD sections in the registry", () => {
	const department = departments.find((item) => item.key === "merch-pd")
	assert.deepEqual([department.label, department.path], ["Merch PD", "/merch-pd"])
	assert.deepEqual(department.combines, ["merch", "purchase", "pd"])
	const paths = getWorkspacePaths(department)
	assert.deepEqual(paths, {
		lots: ["/merch/lots", "/purchase/lots"],
		item_production_details: ["/merch/item-production-details"],
		purchase_orders: ["/purchase/purchase-orders"],
		bill_tracking: ["/merch/bill-tracking", "/purchase/bill-tracking"],
		lotwise_item_profits: ["/pd/lotwise-item-profits"],
	})
	assert.equal(Object.keys(getWorkspacePaths(departments.find((item) => item.key === "merch-purchase"))).length, 18, "other combined departments keep every section")
	assert.deepEqual(locked.workspaces, workspaces)
})

test("a Merch PD layout opens each card, its create flow and records; other sections stay closed", () => {
	const router = loadRouter()
	for (const item of items) {
		assert.ok(isWorkspaceInLayout(item, locked), item.to)
		assert.notEqual(router.resolve(item.to).matched.length, 0, item.to)
		assert.equal(getLockedRedirect(router.resolve(item.to), locked), undefined, item.to)
	}
	for (const path of ["/merch-pd", "/merch/lots/new", "/merch/item-production-details/new", "/purchase/purchase-orders/new", "/pd/lotwise-item-profits/new", "/merch/lots/LOT-1"]) {
		assert.equal(getLockedRedirect(router.resolve(path), locked), undefined, path)
	}
	for (const path of ["/", "/merch", "/purchase", "/pd"]) assert.deepEqual(getLockedRedirect(router.resolve(path), locked), { path: "/merch-pd", replace: true }, path)
	for (const path of ["/merch/work-orders", "/purchase/items", "/pd/products", "/sales/production-orders", "/fabric-store/purchase-orders"]) {
		assert.deepEqual(getLockedRedirect(router.resolve(path), locked), notInLayout(path), path)
	}
})

test("cards for unreadable DocTypes are hidden", () => {
	const boot = { user: { name: "merch@example.com", can_read: ["SD YRP Lot", "YRP Item Production Detail"] } }
	assert.equal(canOpenList("/pd/lotwise-item-profits", boot), false)
	assert.equal(canOpenList("/purchase/purchase-orders", boot), false)
	assert.equal(canOpenList("/merch/lots", boot), true)
	const sections = { lots: { can_read: true }, item_production_details: { can_read: true }, purchase_orders: { can_read: false } }
	assert.deepEqual(visibleMerchLauncherItems(sections, items).map((item) => item.key), ["lots", "item_production_details"])
	assert.match(source("../src/departments/MerchPd.vue"), /:load-capabilities="getMerchPdCapabilities"/)
	assert.match(source("../src/api/merch.js"), /essdee_yrp\.merch_pd\.web_workspace\.get_capabilities/)
})

test("PD opens the LaySheet Planner list, editor and records inside PD", () => {
	const router = loadRouter()
	const pdWorkspaces = JSON.parse(JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.experience_key === "pd").config).experience_props.workspaces
	const pdLocked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "pd" }, config: { experience_props: { workspaces: pdWorkspaces } } } })
	const card = pdLauncherItems().find((item) => item.key === "lay_sheet_planner")
	assert.deepEqual([card.label, card.to], ["LaySheet Planner", "/pd/lay-sheet-planner"])
	assert.ok(pdWorkspaces.includes("lay_sheet_planner"))
	for (const [path, name] of [["/pd/lay-sheet-planner", PD_ROUTES.laySheetPlanners], ["/pd/lay-sheet-planner/new", PD_ROUTES.laySheetPlannerNew], ["/pd/lay-sheet-planner/CLP-1", PD_ROUTES.laySheetPlanner]]) {
		const route = router.resolve(path)
		assert.equal(route.name, name, path)
		assert.equal(getLockedRedirect(route, pdLocked), undefined, path)
	}
	assert.deepEqual(JSON.parse(JSON.stringify(router.resolve("/pd/lay-sheet-planner").matched.at(-1).props.default)), {
		backTo: "/pd", backLabel: "PD", viewRouteName: PD_ROUTES.laySheetPlanner, newRouteName: PD_ROUTES.laySheetPlannerNew,
	})
	assert.equal(router.resolve("/cutting/lay-sheet-planner").matched.at(-1).components.default, router.resolve("/pd/lay-sheet-planner").matched.at(-1).components.default, "PD reuses the Cutting planner list")
	assert.equal(webDocumentPath("SD YRP Cutting Laysheet Planner", "CLP/1", "/web/pd/lay-sheet-planner"), "/web/pd/lay-sheet-planner/CLP%2F1")
	assert.equal(canOpenList("/pd/lay-sheet-planner", { user: { name: "pd@example.com", can_read: ["SD YRP Product"] } }), false)
	assert.deepEqual(getLockedRedirect(router.resolve("/cutting/lay-sheet-planner"), pdLocked), notInLayout("/cutting/lay-sheet-planner"))
})
