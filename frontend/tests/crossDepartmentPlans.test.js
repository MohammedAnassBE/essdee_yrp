import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import * as accountsViews from "../src/departments/accounts/accountsViews.js"
import * as storeWorkspaces from "../src/departments/fabric-store/storeWorkspaces.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"
import { MERCH_PD_ROUTES } from "../src/departments/merch-pd/merchPdRoutes.js"
import { MERCH_PURCHASE_ROUTES } from "../src/departments/merch-purchase/merchPurchaseRoutes.js"
import { QUALITY_ROUTES } from "../src/departments/quality/qualityRoutes.js"
import { getLockedDepartment, getLockedRedirect, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { getListDoctype } from "../src/router/listPermission.js"
import { webDocumentPath } from "../src/router/webDocumentRoutes.js"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const stub = (name) => (props, { slots }) => Vue.h(name, props, slots.default?.())
const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const layouts = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json"))
const department = (key) => departments.find((item) => item.key === key)
const plain = (value) => JSON.parse(JSON.stringify(value))

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES: accountsViews.ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, MERCH_PD_ROUTES, MERCH_PURCHASE_ROUTES, QUALITY_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH: "/no-permission" }
	vm.runInNewContext(routerSource, context)
	return context.router
}

function lockedLayout(key) {
	const workspaces = JSON.parse(layouts.find((row) => row.experience_key === key).config).experience_props.workspaces
	return getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: key }, config: { experience_props: { workspaces } } } })
}

async function finishingCards(sections) {
	const page = loadComponent(resolve("frontend/src/departments/Finishing.vue"), {
		"../api/finishing.js": { getFinishingCapabilities: async () => ({ sections }) },
		"../components/DepartmentPage.vue": stub("department"),
		"../components/common/WorkspaceLauncher.vue": stub("launcher"),
		"../components/common/WorkspaceLoadError.vue": stub("error"),
		"./fabric-store/storeWorkspaces.js": storeWorkspaces,
	})
	const root = mountComponent(page, {})
	await tick()
	return nodes(root, "launcher")[0].props.items
}

async function sewingCards(sections) {
	const shell = (props, { slots }) => Vue.h("shell", props, slots.default?.({ capabilities: { sections }, supplier: "Unit 1" }))
	const root = mountComponent(loadComponent(resolve("frontend/src/departments/sewing/SewingLauncher.vue"), {
		"../../components/common/WorkspaceLauncher.vue": stub("launcher"),
		"./SewingBackLink.vue": stub("back"), "./SewingWorkspaceShell.vue": shell, "./SewingUnitPicker.vue": stub("picker"), "../fabric-store/storeWorkspaces.js": storeWorkspaces,
	}), {})
	await tick()
	return nodes(root, "launcher")[0].props.items
}

test("Finishing shows the Sewing Plan card after Finishing Plan only when the server allows it", async () => {
	const cards = await finishingCards({ plans: { can_read: true }, sewing_plans: { can_read: true } })
	assert.deepEqual(cards.map((item) => item.key), ["plans", "sewing_plans"])
	assert.equal(cards[1].label, "Sewing Plan")
	assert.equal(cards[1].to, "/finishing/sewing-plans")
	assert.ok(!(await finishingCards({ plans: { can_read: true } })).some((item) => item.key === "sewing_plans"))
})

test("Sewing shows the Finishing Plan card after Sewing Plan only when the server allows it", async () => {
	const cards = await sewingCards({ plans: { can_read: true }, finishing_plans: { can_read: true } })
	assert.deepEqual(cards.map((item) => item.key), ["plans", "finishing_plans"])
	assert.equal(cards[1].label, "Finishing Plan")
	assert.equal(cards[1].to.path, "/sewing/finishing-plans")
	assert.ok(!(await sewingCards({ plans: { can_read: true } })).some((item) => item.key === "finishing_plans"))
})

test("Finishing opens the shared Sewing Plan workspace inside Finishing", () => {
	const router = loadRouter()
	const page = router.resolve("/finishing/sewing-plans")
	assert.equal(page.name, "finishing-sewing-plans")
	assert.equal(page.matched.at(-1).components.default, router.resolve("/sewing/plans").matched.at(-1).components.default)
	assert.deepEqual(plain(page.matched.at(-1).props.default), { backTo: "/finishing", backLabel: "Finishing" })
	assert.equal(getListDoctype("/finishing/sewing-plans"), "SD YRP Sewing Plan")
})

test("Sewing opens the shared Finishing Plan list and page inside Sewing", () => {
	const router = loadRouter()
	const list = router.resolve("/sewing/finishing-plans")
	assert.equal(list.name, "sewing-finishing-plans")
	assert.equal(list.matched.at(-1).components.default, router.resolve("/finishing/plans").matched.at(-1).components.default)
	assert.deepEqual(plain(list.matched.at(-1).props.default), { backTo: "/sewing", backLabel: "Sewing", viewRouteName: "sewing-finishing-plan" })
	const view = router.resolve("/sewing/finishing-plans/FP-1")
	assert.equal(view.name, "sewing-finishing-plan")
	assert.equal(view.matched.at(-1).components.default, router.resolve("/finishing/plans/FP-1").matched.at(-1).components.default)
	assert.deepEqual(plain(view.matched.at(-1).props.default), { backTo: "/sewing/finishing-plans", backLabel: "Finishing Plans" })
	assert.equal(getListDoctype("/sewing/finishing-plans"), "SD YRP Finishing Plan")
})

test("Finishing Plan links stay inside Sewing while other departments keep their pages", () => {
	assert.equal(webDocumentPath("SD YRP Finishing Plan", "FP/1", "/web/sewing/finishing-plans"), "/web/sewing/finishing-plans/FP%2F1")
	assert.equal(webDocumentPath("SD YRP Finishing Plan", "FP/1", "/web/sewing/plans"), "/web/sewing/finishing-plans/FP%2F1")
	assert.equal(webDocumentPath("SD YRP Finishing Plan", "FP/1", "/web/finishing/sewing-plans"), "/web/finishing/plans/FP%2F1")
	assert.equal(webDocumentPath("SD YRP Finishing Plan", "FP/1", "/web/planning/finishing-plans"), "/web/planning/finishing-plans/FP%2F1")
})

test("the Sewing and Finishing layouts own the other department's plan pages", () => {
	const router = loadRouter()
	assert.deepEqual(getWorkspacePaths(department("finishing")).sewing_plans, ["/finishing/sewing-plans"])
	assert.deepEqual(getWorkspacePaths(department("sewing")).finishing_plans, ["/sewing/finishing-plans"])
	const finishing = lockedLayout("finishing")
	const sewing = lockedLayout("sewing")
	assert.ok(finishing.workspaces.includes("sewing_plans"))
	assert.ok(sewing.workspaces.includes("finishing_plans"))
	assert.equal(getLockedRedirect(router.resolve("/finishing/sewing-plans"), finishing), undefined)
	assert.equal(getLockedRedirect(router.resolve("/sewing/finishing-plans"), sewing), undefined)
	assert.equal(getLockedRedirect(router.resolve("/sewing/finishing-plans/FP-1"), sewing), undefined)
})
