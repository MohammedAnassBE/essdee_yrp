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
const PATHS = { rework_details: "/planning/rework-details", purchase_orders: "/planning/purchase-orders" }
const props = (route) => JSON.parse(JSON.stringify(route.matched.at(-1).props.default))

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	return context.router
}

test("Planning shows Rework Details and Purchase Order cards under its own paths", () => {
	const paths = getWorkspacePaths(departments.find((item) => item.key === "planning"))
	for (const [key, path] of Object.entries(PATHS)) {
		assert.equal(PLANNING_WORKSPACES.find((item) => item.key === key).to, path)
		assert.deepEqual(visiblePlanningWorkspaces({ [key]: { can_read: true } }).map((item) => item.key), [key])
		assert.deepEqual(visiblePlanningWorkspaces({ [key]: { can_read: false } }), [])
		assert.deepEqual(paths[key], [path])
	}
})

test("Planning reuses the Finishing Rework Details page and the store Purchase Order pages", () => {
	const router = loadRouter()
	const rework = router.resolve(PATHS.rework_details)
	assert.equal(rework.name, PLANNING_ROUTES.reworkDetails)
	assert.deepEqual(props(rework), { backTo: "/planning", backLabel: "Planning" })
	const list = router.resolve(PATHS.purchase_orders)
	assert.equal(list.name, PLANNING_ROUTES.purchaseOrders)
	assert.deepEqual(props(list), { section: "purchase_orders", storeName: "Planning", basePath: "/planning", purchaseOrderViewRouteName: PLANNING_ROUTES.purchaseOrder })
	const record = router.resolve(`${PATHS.purchase_orders}/PO-0001`)
	assert.equal(record.name, PLANNING_ROUTES.purchaseOrder)
	assert.equal(props(record).backTo, PATHS.purchase_orders)
	assert.match(source("../src/departments/finishing/FinishingReworkDetails.vue"), /:back-to="backTo" :back-label="backLabel"/)
})

test("the Production Planner layout opens Rework Details and Purchase Order", () => {
	const layout = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.name === "Production Planner")
	const workspaces = JSON.parse(layout.config).experience_props.workspaces
	const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "planning" }, config: { experience_props: { workspaces } } } })
	for (const [key, path] of Object.entries(PATHS)) {
		assert.ok(isWorkspaceInLayout({ key, to: path }, locked))
		assert.equal(getLockedRedirect(loadRouter().resolve(path), locked), undefined)
	}
	assert.equal(getLockedRedirect(loadRouter().resolve(`${PATHS.purchase_orders}/PO-0001`), locked), undefined)
})

test("Finishing no longer offers Rework Grouped Details", () => {
	assert.doesNotMatch(source("../src/departments/Finishing.vue"), /rework_groups|Rework Grouped Details/)
	assert.equal(loadRouter().resolve("/finishing/rework-groups").name, undefined)
	const finishing = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.name === "Finishing")
	assert.ok(!JSON.parse(finishing.config).experience_props.workspaces.includes("rework_groups"))
})
