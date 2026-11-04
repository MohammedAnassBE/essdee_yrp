import assert from "node:assert/strict"
import { readdirSync, readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import { ACCOUNTS_ROUTES, accountsLauncherItems } from "../src/departments/accounts/accountsViews.js"
import { merchPdLauncherItems } from "../src/departments/merch-pd/merchPdViews.js"
import { MERCH_PD_ROUTES } from "../src/departments/merch-pd/merchPdRoutes.js"
import { merchPurchaseLauncherItems } from "../src/departments/merch-purchase/merchPurchaseViews.js"
import { MERCH_PURCHASE_ROUTES } from "../src/departments/merch-purchase/merchPurchaseRoutes.js"
import { MERCH_ROUTES, merchLauncherItems } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES, PLANNING_WORKSPACES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES, purchaseLauncherItems } from "../src/departments/purchase/purchaseViews.js"
import { qualityLauncherItems } from "../src/departments/quality/qualityWorkspaces.js"
import { QUALITY_ROUTES } from "../src/departments/quality/qualityRoutes.js"
import { departments } from "../src/departments/registry.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const SHARED_IMPORTS = ["../../fabric-store/FabricDocumentWorkspace.vue", "../../fabric-store/WorkOrderItemMatrix.vue"]
const WORKSPACES = [
	{ key: "purchase", prefix: "/purchase", routes: PURCHASE_ROUTES, cards: purchaseLauncherItems, canCreate: true },
	{ key: "planning", prefix: "/planning", routes: PLANNING_ROUTES, cards: () => PLANNING_WORKSPACES, canCreate: false },
	{ key: "merch", prefix: "/merch", routes: MERCH_ROUTES, cards: merchLauncherItems, canCreate: true },
	{ key: "merch-pd", prefix: "/merch-pd", routes: MERCH_PD_ROUTES, cards: merchPdLauncherItems, canCreate: true },
	{ key: "merch-purchase", prefix: "/merch-purchase", routes: MERCH_PURCHASE_ROUTES, cards: merchPurchaseLauncherItems, canCreate: true },
	{ key: "accounts", prefix: "/accounts", routes: ACCOUNTS_ROUTES, cards: accountsLauncherItems, canCreate: true },
	{ key: "quality", prefix: "/quality", routes: QUALITY_ROUTES, cards: qualityLauncherItems, canCreate: false },
]

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, MERCH_PD_ROUTES, MERCH_PURCHASE_ROUTES, QUALITY_ROUTES, LAYOUT_UNAVAILABLE_PATH: "/not-in-your-layout",
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	return context.router
}

function lotFiles(workspace) {
	const folder = new URL(`../src/departments/${workspace}/lot/`, import.meta.url)
	return readdirSync(folder).filter((name) => /\.(vue|js)$/.test(name)).map((name) => ({ name, text: readFileSync(new URL(name, folder), "utf8") }))
}

for (const workspace of WORKSPACES) {
	test(`${workspace.key} Lot imports nothing from another workspace's folder`, () => {
		for (const file of lotFiles(workspace.key)) {
			const imports = [...file.text.matchAll(/(?:from|import)\s+"(\.\.\/\.\.\/[a-z][^"]*)"/g)].map((match) => match[1])
			assert.deepEqual(imports.filter((path) => !SHARED_IMPORTS.includes(path)), [], `${workspace.key}/lot/${file.name}`)
		}
	})

	test(`${workspace.key} Lot card, routes and links stay under ${workspace.prefix}`, () => {
		const router = loadRouter()
		assert.equal(workspace.cards().find((item) => item.key === "lots").to, `${workspace.prefix}/lots`)
		assert.equal(router.resolve(`${workspace.prefix}/lots`).name, workspace.routes.lots)
		assert.equal(router.resolve(`${workspace.prefix}/lots/LOT-1`).name, workspace.routes.lot)
		assert.equal(router.resolve(`${workspace.prefix}/lots/LOT-1/edit`).name, workspace.routes.lotEdit)
		assert.equal(router.resolve(`${workspace.prefix}/lots/new`).name, workspace.canCreate ? workspace.routes.lotNew : workspace.routes.lot)
		const backLinks = lotFiles(workspace.key).flatMap((file) => [...file.text.matchAll(/back-to="([^"]*)"/g)].map((match) => match[1]))
		assert.ok(backLinks.length)
		for (const backTo of backLinks) assert.match(backTo, new RegExp(`^${workspace.prefix}(/lots)?$`))
		assert.equal(webDocumentPath("SD YRP Lot", "LOT-2", `/web${workspace.prefix}/lots/LOT-1`), `/web${workspace.prefix}/lots/LOT-2`)
	})
}
