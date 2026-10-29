import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES, PLANNING_WORKSPACES, visiblePlanningWorkspaces } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const PATH = "/planning/stock-transfers"

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	return context.router
}

test("Planning shows the shared Stock Transfers section under its own path", () => {
	const card = PLANNING_WORKSPACES.find((item) => item.key === "stock_transfers")
	assert.deepEqual([card.label, card.to], ["Stock Transfers", PATH])
	assert.deepEqual(visiblePlanningWorkspaces({ stock_transfers: { can_read: true } }).map((item) => item.key), ["stock_transfers"])
	assert.deepEqual(visiblePlanningWorkspaces({ stock_transfers: { can_read: false } }), [])
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "planning")).stock_transfers, [PATH])
	const route = loadRouter().resolve(PATH)
	assert.equal(route.name, PLANNING_ROUTES.stockTransfers)
	assert.deepEqual(JSON.parse(JSON.stringify(route.matched.at(-1).props.default)), { section: "stock_transfers", storeName: "Planning", basePath: "/planning" })
})

test("the Planning Stock Transfers section lists Stock Update, Stock Reconciliation, Stock Entry and Lot Transfer", () => {
	const component = source("../src/departments/fabric-store/FabricStockTransfers.vue")
	for (const label of ["Stock Entry", "Stock Reconciliation", "Stock Update", "Lot Transfer"]) assert.match(component, new RegExp(`label: "${label}"`))
	const backend = source("../../essdee_yrp/planning/web_workspace.py")
	assert.match(backend, /"stock_transfers": \{"can_read": True, \*\*fabric_store_sections\["stock_transfers"\]\}/)
})

test("the Production Planner layout opens Stock Transfers", () => {
	const layout = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.name === "Production Planner")
	const workspaces = JSON.parse(layout.config).experience_props.workspaces
	const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "planning" }, config: { experience_props: { workspaces } } } })
	assert.ok(workspaces.includes("stock_transfers"))
	assert.ok(isWorkspaceInLayout({ key: "stock_transfers", to: PATH }, locked))
	assert.equal(getLockedRedirect(loadRouter().resolve(PATH), locked), undefined)
})
