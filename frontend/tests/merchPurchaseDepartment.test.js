import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"
import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"

import { combinedDeskReports, departmentDeskReports } from "../src/components/reports/deskReportConfig.js"
import { merchPurchaseLauncherItems } from "../src/departments/merch-purchase/merchPurchaseViews.js"
import { MERCH_ROUTES, merchLauncherItems, visibleMerchLauncherItems } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES, PURCHASE_STORE_WORKSPACE_KEYS, purchaseLauncherItems } from "../src/departments/purchase/purchaseViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, isLockedExit, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { canOpenList, getPermissionRedirect, NO_PERMISSION_PATH } from "../src/router/listPermission.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const layout = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.experience_key === "merch-purchase")
const workspaces = JSON.parse(layout.config).experience_props.workspaces
const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "merch-purchase" }, config: { experience_props: { workspaces } } } })
const items = merchPurchaseLauncherItems()
const notInLayout = (from) => ({ path: LAYOUT_UNAVAILABLE_PATH, query: { from }, replace: true })

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH }
	vm.runInNewContext(routerSource, context)
	return context.router
}

test("Merch & Purchase combines every Merch and Purchase card once", () => {
	const keys = items.map((item) => item.key)
	assert.deepEqual(keys, ["lots", "item_production_details", "production_orders", "work_orders", "delivery_challans", "goods_received_notes", "process_costs", "bill_tracking", "purchase_invoices", "items", "item_prices", "purchase_orders", "stock_transfers", "item_conversions", "box_stickers", "excel_stickers", "reports"])
	assert.equal(new Set(keys).size, keys.length)
	for (const key of [...merchLauncherItems(), ...purchaseLauncherItems()].map((item) => item.key).concat(PURCHASE_STORE_WORKSPACE_KEYS)) assert.ok(keys.includes(key), key)
	assert.deepEqual(items.filter((item) => item.label === "Lot").map((item) => item.to), ["/merch/lots"])
	assert.equal(items.find((item) => item.key === "reports").to, "/merch-purchase/reports")
	assert.equal(items.find((item) => item.key === "purchase_orders").to, "/purchase/purchase-orders")
	assert.deepEqual(workspaces, keys, "the shipped layout lists every combined card")
})

test("the department combines Merch and Purchase sections in the registry", () => {
	const department = departments.find((item) => item.key === "merch-purchase")
	assert.equal(department.label, "Merch & Purchase")
	assert.deepEqual(department.combines, ["merch", "purchase"])
	const paths = getWorkspacePaths(department)
	assert.deepEqual(paths.lots, ["/merch/lots", "/purchase/lots"])
	assert.deepEqual(paths.reports, ["/merch-purchase/reports", "/merch/reports", "/purchase/reports"])
	assert.deepEqual(locked.workspaces, workspaces)
	assert.deepEqual(getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "merch-purchase" } } }).workspaces, Object.keys(paths))
})

test("a Merch & Purchase layout opens every combined card, list and create flow", () => {
	const router = loadRouter()
	for (const item of items) {
		assert.ok(isWorkspaceInLayout(item, locked), item.to)
		assert.notEqual(router.resolve(item.to).matched.length, 0, item.to)
		assert.equal(getLockedRedirect(router.resolve(item.to), locked), undefined, item.to)
	}
	for (const path of ["/merch-purchase", "/merch/lots/new", "/purchase/purchase-orders/new", "/merch/production-orders/new", "/purchase/items/new", "/purchase/item-prices/new", "/merch/item-production-details/new", "/merch/lots/LOT-1", "/purchase/lots"]) {
		assert.equal(getLockedRedirect(router.resolve(path), locked), undefined, path)
	}
	assert.equal(router.resolve("/merch-purchase/reports").name, "merch-purchase-reports")
	assert.deepEqual(JSON.parse(JSON.stringify(router.resolve("/merch-purchase/reports").matched.at(-1).props.default)), { department: "merch-purchase" })
})

test("the workspaces page and the combined landings open Merch & Purchase; other departments stay closed", () => {
	const router = loadRouter()
	for (const path of ["/", "/merch", "/purchase"]) assert.deepEqual(getLockedRedirect(router.resolve(path), locked), { path: "/merch-purchase", replace: true }, path)
	for (const path of ["/sales", "/sales/production-orders", "/fabric-store/purchase-orders", "/accounts/purchase-invoices", "/planning/lots"]) {
		assert.deepEqual(getLockedRedirect(router.resolve(path), locked), notInLayout(path), path)
	}
	assert.equal(isLockedExit("/merch", locked), false)
	assert.equal(isLockedExit("/purchase", locked), false)
	assert.equal(isLockedExit("/", locked), true)
	assert.equal(isLockedExit("/sales", locked), true)
	const narrow = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "merch-purchase" }, config: { experience_props: { workspaces: ["lots"] } } } })
	assert.deepEqual(getLockedRedirect(router.resolve("/purchase/purchase-orders"), narrow), notInLayout("/purchase/purchase-orders"))
	assert.equal(getLockedRedirect(router.resolve("/merch/lots"), narrow), undefined)
})

test("cards and list URLs for unreadable DocTypes are hidden from the combined department", () => {
	const boot = { user: { name: "merch@example.com", can_read: ["SD YRP Lot", "Item", "YRP Item Price", "YRP Production Order"] } }
	const card = items.find((item) => item.key === "purchase_orders")
	assert.equal(canOpenList(card.to, boot), false)
	assert.equal(canOpenList(items.find((item) => item.key === "lots").to, boot), true)
	assert.deepEqual(getPermissionRedirect({ path: card.to, fullPath: card.to, params: {} }, boot), {
		path: NO_PERMISSION_PATH, query: { doctype: "Purchase Order", from: card.to }, replace: true,
	})
	const sections = Object.fromEntries(items.map((item) => [item.key, { can_read: item.key !== "items" }]))
	assert.deepEqual(visibleMerchLauncherItems(sections, items).map((item) => item.key), items.map((item) => item.key).filter((key) => key !== "items"))
	assert.deepEqual(visibleMerchLauncherItems({}, items), [])
})

test("the combined Reports page lists Merch and Purchase desk reports once each", () => {
	const capabilities = Object.fromEntries(["grn_report", "grn_summary", "dc_report", "stock_entry_report", "stock_reconciliation_report", "stock_update_report", "purchase_order_log", "lot_purchase_summary", "purchase_order_itemwise"].map((key) => [key, { can_read: true }]))
	const tabs = combinedDeskReports(["merch", "purchase"], capabilities).map((tab) => tab.value)
	assert.equal(new Set(tabs).size, tabs.length)
	assert.deepEqual(new Set(tabs), new Set([...departmentDeskReports("merch", capabilities), ...departmentDeskReports("purchase", capabilities)].map((tab) => tab.value)))
	assert.ok(tabs.includes("grn-report") && tabs.includes("lot-purchase-summary"))
	const page = source("../src/departments/merch/MerchReports.vue")
	assert.match(page, /"merch-purchase": \{ load: getMerchPurchaseCapabilities, deskDepartments: \["merch", "purchase"\] \}/)
	assert.match(page, /key: "stock_balance"/)
	assert.match(page, /key: "lot_cut_quantity"/)
	assert.match(page, /reports\.value\[report\.key\]\?\.can_read/)
})

test("Purchase shows Vendor Bill Tracking once, with routes and record links kept inside Purchase", () => {
	const card = purchaseLauncherItems().find((item) => item.key === "bill_tracking")
	assert.deepEqual([card.label, card.to], ["Vendor Bill Tracking", "/purchase/bill-tracking"])
	assert.deepEqual(items.filter((item) => item.key === "bill_tracking").map((item) => item.to), ["/merch/bill-tracking"])
	const router = loadRouter()
	for (const [path, name] of [["/purchase/bill-tracking", PURCHASE_ROUTES.billTrackings], ["/purchase/bill-tracking/new", PURCHASE_ROUTES.billTrackingNew], ["/purchase/bill-tracking/BT-1", PURCHASE_ROUTES.billTracking], ["/purchase/bill-tracking/BT-1/edit", PURCHASE_ROUTES.billTrackingEdit]]) {
		assert.equal(router.resolve(path).name, name, path)
	}
	assert.equal(webDocumentPath("YRP Bill Tracking", "BT/1", "/web/purchase/bill-tracking"), "/web/purchase/bill-tracking/BT%2F1")
	const boot = { user: { name: "purchase@example.com", can_read: ["SD YRP Lot"] } }
	assert.equal(canOpenList(card.to, boot), false)
	assert.equal(canOpenList(card.to, { user: { name: "purchase@example.com", can_read: ["YRP Bill Tracking"] } }), true)
	const purchaseLayout = JSON.parse(JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.experience_key === "purchase").config).experience_props.workspaces
	const purchaseLocked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "purchase" }, config: { experience_props: { workspaces: purchaseLayout } } } })
	assert.ok(purchaseLayout.includes("bill_tracking"))
	assert.equal(getLockedRedirect(router.resolve("/purchase/bill-tracking/BT-1"), purchaseLocked), undefined)
})
