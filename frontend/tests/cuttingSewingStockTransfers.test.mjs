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
import { sewingReportTabs } from "../src/departments/departmentReports.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const CASES = [
	{ department: "cutting", key: "stock-transfers", path: "/cutting/stock-transfers", storeName: "Cutting", launcher: "../src/departments/Cutting.vue", layout: "Cutting", backend: "../../essdee_yrp/cutting/web_capabilities.py" },
	{ department: "sewing", key: "stock_transfers", path: "/sewing/stock-transfers", storeName: "Sewing", launcher: "../src/departments/sewing/SewingLauncher.vue", layout: "Sewing", backend: "../../essdee_yrp/sewing/web_workspace.py" },
]

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	return context.router
}

for (const item of CASES) {
	test(`${item.storeName} shows the shared Stock Transfers section under its own path`, () => {
		assert.match(source(item.launcher), new RegExp(`key: "${item.key}", label: "Stock Transfers",[^}]*"${item.path}"`))
		assert.match(source(item.backend), /get_stock_transfers_section\(\)/)
		assert.deepEqual(getWorkspacePaths(departments.find((department) => department.key === item.department))[item.key], [item.path])
		const route = loadRouter().resolve(item.path)
		assert.equal(route.name, `${item.department}-stock-transfers`)
		assert.deepEqual(JSON.parse(JSON.stringify(route.matched.at(-1).props.default)), { section: "stock_transfers", storeName: item.storeName, basePath: `/${item.department}` })
	})

	test(`the ${item.layout} layout opens Stock Transfers`, () => {
		const layout = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.name === item.layout)
		const workspaces = JSON.parse(layout.config).experience_props.workspaces
		const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: item.department }, config: { experience_props: { workspaces } } } })
		assert.ok(workspaces.includes(item.key))
		assert.ok(isWorkspaceInLayout({ key: item.key, to: item.path }, locked))
		assert.equal(getLockedRedirect(loadRouter().resolve(item.path), locked), undefined)
	})
}

test("Sewing reports show Stock Balance only when the report is readable", () => {
	assert.deepEqual(sewingReportTabs({ stock_balance: { can_read: true } }).map((report) => report.value), ["stock-balance"])
	assert.deepEqual(sewingReportTabs({ stock_balance: { can_read: false } }), [])
	assert.match(source("../src/departments/sewing/SewingReportsWorkspace.vue"), /<StockBalanceReport v-else-if="report.value === 'stock-balance'" \/>/)
	assert.match(source("../../essdee_yrp/sewing/web_workspace.py"), /can_run_report\("YRP Stock Balance"\)/)
})
