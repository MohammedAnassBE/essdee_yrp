import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { qualityLauncherItems } from "../src/departments/quality/qualityWorkspaces.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const layout = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.experience_key === "quality")
const workspaces = JSON.parse(layout.config).experience_props.workspaces
const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "quality" }, config: { experience_props: { workspaces } } } })
const items = qualityLauncherItems()
const notInLayout = (from) => ({ path: LAYOUT_UNAVAILABLE_PATH, query: { from }, replace: true })

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	return context.router
}

test("Quality shows its own cards, then the Planning, Merch, PD and Accounts pages, then Reports", () => {
	assert.deepEqual(items.map((item) => [item.key, item.to]), [
		["inspections", "/quality/inspections"],
		["work_orders", "/quality/work-orders"],
		["delivery_challans", "/quality/delivery-challans"],
		["goods_received_notes", "/quality/goods-received-notes"],
		["cutting_plans", "/planning/cutting-plans"],
		["lots", "/planning/lots"],
		["sewing_plans", "/planning/sewing-plans"],
		["finishing_plans", "/planning/finishing-plans"],
		["process_costs", "/merch/process-costs"],
		["products", "/pd/products"],
		["lotwise_item_profits", "/pd/lotwise-item-profits"],
		["debits", "/accounts/debits"],
		["reports", "/quality/reports"],
	])
	assert.deepEqual(workspaces, items.map((item) => item.key), "the shipped layout lists every card")
	assert.deepEqual(locked.workspaces, workspaces)
})

test("the Quality layout opens each card and its records; other sections of the source departments stay closed", () => {
	const router = loadRouter()
	for (const item of items) {
		assert.ok(isWorkspaceInLayout(item, locked), item.to)
		assert.notEqual(router.resolve(item.to).matched.length, 0, item.to)
		assert.equal(getLockedRedirect(router.resolve(item.to), locked), undefined, item.to)
	}
	for (const path of ["/planning/cutting-plans/CP-1", "/planning/lots/LOT-1", "/merch/process-costs/PC-1", "/pd/products/P-1", "/accounts/debits/WOD-1"]) {
		assert.equal(getLockedRedirect(router.resolve(path), locked), undefined, path)
	}
	for (const path of ["/", "/planning", "/merch", "/pd", "/accounts"]) assert.deepEqual(getLockedRedirect(router.resolve(path), locked), { path: "/quality", replace: true }, path)
	for (const path of ["/planning/work-orders", "/planning/production-orders", "/merch/item-production-details", "/pd/product-releases", "/accounts/purchase-invoices", "/accounts/reports"]) {
		assert.deepEqual(getLockedRedirect(router.resolve(path), locked), notInLayout(path), path)
	}
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "quality")).lots, ["/planning/lots", "/merch/lots"])
})
