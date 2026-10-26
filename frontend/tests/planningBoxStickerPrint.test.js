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
import { canOpenList, NO_PERMISSION_PATH } from "../src/router/listPermission.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const PATH = "/planning/box-sticker-prints"

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH }
	vm.runInNewContext(routerSource, context)
	return context.router
}

test("Planning shows the shared Box Sticker Print section under its own path", () => {
	const card = PLANNING_WORKSPACES.find((item) => item.key === "box_stickers")
	assert.deepEqual([card.label, card.to], ["Box Sticker Print", PATH])
	assert.deepEqual(visiblePlanningWorkspaces({ box_stickers: { can_read: true } }).map((item) => item.key), ["box_stickers"])
	assert.deepEqual(visiblePlanningWorkspaces({ box_stickers: { can_read: false } }), [])
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "planning")).box_stickers, [PATH])
	const route = loadRouter().resolve(PATH)
	assert.equal(route.name, PLANNING_ROUTES.boxStickers)
	assert.deepEqual(JSON.parse(JSON.stringify(route.matched.at(-1).props.default)), { section: "box_stickers", backTo: "/planning", backLabel: "Planning", newRouteName: PLANNING_ROUTES.boxStickerNew, viewRouteName: PLANNING_ROUTES.boxSticker })
	assert.match(source("../src/router/index.js"), /path: "\/planning\/box-sticker-prints", name: PLANNING_ROUTES\.boxStickers, component: CutPanelStoreSection,/)
})

test("the Production Planner layout opens Box Sticker Print and the list needs its read permission", () => {
	const layout = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.name === "Production Planner")
	const workspaces = JSON.parse(layout.config).experience_props.workspaces
	const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "planning" }, config: { experience_props: { workspaces } } } })
	assert.ok(workspaces.includes("box_stickers"))
	assert.ok(isWorkspaceInLayout({ key: "box_stickers", to: PATH }, locked))
	assert.equal(getLockedRedirect(loadRouter().resolve(PATH), locked), undefined)
	assert.equal(canOpenList(PATH, { user: { name: "planner@example.com", can_read: ["SD YRP Box Sticker Print"] } }), true)
	assert.equal(canOpenList(PATH, { user: { name: "planner@example.com", can_read: ["SD YRP Lot"] } }), false)
})
