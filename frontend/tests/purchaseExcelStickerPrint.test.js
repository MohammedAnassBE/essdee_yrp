import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"
import { merchPurchaseLauncherItems } from "../src/departments/merch-purchase/merchPurchaseViews.js"
import { MERCH_ROUTES, visibleMerchLauncherItems } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { storeWorkspaces } from "../src/departments/fabric-store/storeWorkspaces.js"
import { PURCHASE_REPORT_KEYS, PURCHASE_ROUTES, PURCHASE_STORE_WORKSPACE_KEYS } from "../src/departments/purchase/purchaseViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, isWorkspaceInLayout, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { canOpenList, getPermissionRedirect, NO_PERMISSION_PATH } from "../src/router/listPermission.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const PATH = "/purchase/excel-sticker-prints"
const DOCTYPE = "YRP Excel Sticker Print"
const layouts = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json"))
const lockedFor = (key) => {
	const workspaces = JSON.parse(layouts.find((row) => row.experience_key === key).config).experience_props.workspaces
	return getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: key }, config: { experience_props: { workspaces } } } })
}

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH }
	vm.runInNewContext(routerSource, context)
	return context.router
}

test("Purchase shows an Excel Sticker Print card next to Box Sticker Print", () => {
	assert.ok(PURCHASE_STORE_WORKSPACE_KEYS.includes("excel_stickers"))
	const cards = storeWorkspaces("/purchase", PURCHASE_REPORT_KEYS).filter((item) => PURCHASE_STORE_WORKSPACE_KEYS.includes(item.key))
	const keys = cards.map((item) => item.key)
	assert.equal(keys.indexOf("excel_stickers"), keys.indexOf("box_stickers") + 1)
	const card = cards.find((item) => item.key === "excel_stickers")
	assert.equal(card.label, "Excel Sticker Print")
	assert.equal(card.to, PATH)
	assert.equal(merchPurchaseLauncherItems().find((item) => item.key === "excel_stickers").to, PATH)
})

test("the Purchase route opens the shared Excel Sticker Print section", () => {
	const route = loadRouter().resolve(PATH)
	assert.equal(route.name, "purchase-excel-stickers")
	assert.deepEqual(JSON.parse(JSON.stringify(route.matched.at(-1).props.default)), { section: "excel_stickers", backTo: "/purchase", backLabel: "Purchase" })
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "purchase")).excel_stickers, [PATH])
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "merch-purchase")).excel_stickers, [PATH])
	assert.match(source("../src/departments/FabricStore.vue"), /CUT_PANEL_STICKER_KEYS = \["box_stickers", "excel_stickers"\]/)
})

test("the Purchase and Merch & Purchase layouts open the Excel Sticker Print card", () => {
	const router = loadRouter()
	for (const key of ["purchase", "merch-purchase"]) {
		const locked = lockedFor(key)
		assert.ok(locked.workspaces.includes("excel_stickers"), key)
		assert.ok(isWorkspaceInLayout({ key: "excel_stickers", to: PATH }, locked), key)
		assert.equal(getLockedRedirect(router.resolve(PATH), locked), undefined, key)
	}
	const narrow = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "purchase" }, config: { experience_props: { workspaces: ["box_stickers"] } } } })
	assert.deepEqual(getLockedRedirect(router.resolve(PATH), narrow), { path: LAYOUT_UNAVAILABLE_PATH, query: { from: PATH }, replace: true })
})

test("the card and list need read permission on YRP Excel Sticker Print", () => {
	const allowed = { user: { name: "buyer@example.com", can_read: [DOCTYPE] } }
	const denied = { user: { name: "buyer@example.com", can_read: ["SD YRP Box Sticker Print"] } }
	assert.equal(canOpenList(PATH, allowed), true)
	assert.equal(canOpenList(PATH, denied), false)
	assert.deepEqual(getPermissionRedirect({ path: PATH, fullPath: PATH, params: {} }, denied), {
		path: NO_PERMISSION_PATH, query: { doctype: DOCTYPE, from: PATH }, replace: true,
	})
	const items = merchPurchaseLauncherItems()
	const readable = (excel) => Object.fromEntries(items.map((item) => [item.key, { can_read: item.key !== "excel_stickers" || excel }]))
	assert.ok(visibleMerchLauncherItems(readable(true), items).some((item) => item.key === "excel_stickers"))
	assert.ok(!visibleMerchLauncherItems(readable(false), items).some((item) => item.key === "excel_stickers"))
})
