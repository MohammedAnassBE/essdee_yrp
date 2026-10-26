import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import vm from "node:vm"
import { createMemoryHistory, createRouter } from "vue-router"

import { Vue } from "../../scripts/helpers/vue_renderer.mjs"
import { ACCOUNTS_ROUTES } from "../src/departments/accounts/accountsViews.js"
import { MERCH_ROUTES } from "../src/departments/merch/merchViews.js"
import { PD_ROUTES } from "../src/departments/pd/pdViews.js"
import { PLANNING_ROUTES } from "../src/departments/planning/planningViews.js"
import { PURCHASE_ROUTES } from "../src/departments/purchase/purchaseViews.js"
import { departments } from "../src/departments/registry.js"
import { getLockedDepartment, getLockedRedirect, LAYOUT_UNAVAILABLE_PATH } from "../src/router/departmentLock.js"
import { NO_PERMISSION_PATH } from "../src/router/listPermission.js"
import { withNewDocumentDefaults } from "../src/utils/newDocumentDefaults.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const PAGE = source("../src/departments/cut-panel-store/BoxStickerPrintPage.vue")
const LIST = source("../src/departments/cut-panel-store/BoxStickerPrints.vue")
const placements = [
	["/cut-panel-store/box-sticker-prints", "cut-panel-box-stickers", "cut-panel-box-sticker-print-new", "cut-panel-box-sticker-print"],
	["/planning/box-sticker-prints", PLANNING_ROUTES.boxStickers, PLANNING_ROUTES.boxStickerNew, PLANNING_ROUTES.boxSticker],
	["/purchase/box-sticker-prints", "purchase-box-stickers", "purchase-box-sticker-print-new", "purchase-box-sticker-print"],
]

function loadRouter() {
	const routerSource = source("../src/router/index.js").replace(/^import .*\n/gm, "")
		.replace(/export function /g, "function ").replace("export default router", "globalThis.router = router")
	const context = { ACCOUNTS_ROUTES, departments, PD_ROUTES, PURCHASE_ROUTES, PLANNING_ROUTES, MERCH_ROUTES, LAYOUT_UNAVAILABLE_PATH,
		createRouter, createWebHistory: () => createMemoryHistory("/web/"), getLockedRedirect: () => undefined, getPermissionRedirect: () => undefined, NO_PERMISSION_PATH }
	vm.runInNewContext(routerSource, context)
	return context.router
}

const plain = (value) => JSON.parse(JSON.stringify(value))
const pageProps = (route) => {
	const props = route.matched.at(-1).props.default
	return plain(typeof props === "function" ? props(route) : props)
}

test("every Box Sticker Print list opens full new and document pages under its own path", () => {
	const router = loadRouter()
	for (const [listPath, listName, newRouteName, viewRouteName] of placements) {
		const list = router.resolve(listPath)
		assert.equal(list.name, listName)
		assert.deepEqual([pageProps(list).newRouteName, pageProps(list).viewRouteName], [newRouteName, viewRouteName], listPath)
		const expected = { backTo: listPath, backLabel: "Box Sticker Prints", newRouteName, viewRouteName }
		const created = router.resolve(`${listPath}/new`)
		assert.equal(created.name, newRouteName)
		assert.deepEqual(pageProps(created), expected)
		const opened = router.resolve(`${listPath}/BSP-2026-00001`)
		assert.equal(opened.name, viewRouteName)
		assert.deepEqual(pageProps(opened), { boxStickerPrintId: "BSP-2026-00001", ...expected })
	}
})

test("the Production Planner layout allows the Box Sticker Print pages", () => {
	const layout = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.name === "Production Planner")
	const workspaces = JSON.parse(layout.config).experience_props.workspaces
	const locked = getLockedDepartment({ ui_config: { meta: { render_mode: "Registered Experience", experience_key: "planning" }, config: { experience_props: { workspaces } } } })
	const router = loadRouter()
	for (const path of ["/planning/box-sticker-prints/new", "/planning/box-sticker-prints/BSP-1"]) assert.equal(getLockedRedirect(router.resolve(path), locked), undefined, path)
})

test("the list opens the page instead of a dialog", () => {
	assert.doesNotMatch(LIST, /Dialog/)
	assert.match(LIST, /router\.push\(\{ name: newRouteName \}\)/)
	assert.match(LIST, /openListDocument\(router, row, snapshot, \{ routeName: props\.viewRouteName, paramName: "boxStickerPrintId" \}\)/)
})

test("the page offers shared Duplicate, default-format Print and Delete back to its list", () => {
	assert.match(PAGE, /useDuplicateAction\(\{[\s\S]*?newRouteName: \(\) => props\.newRouteName,[\s\S]*?name: \(\) => record\.value\?\.name,/)
	assert.match(PAGE, /<DocumentPrintButton v-if="record\?\.name" doctype="SD YRP Box Sticker Print"/)
	assert.match(PAGE, /<DocumentDeleteButton v-if="record\?\.name"[^>]*:redirect-to="backTo"/)
	assert.match(PAGE, /usePageTitle\(\(\) => record\.value\?\.name\)/)
	assert.doesNotMatch(PAGE, /<Dialog\b/)
})

function page(bindings) {
	const script = PAGE.split("<script setup>")[1].split("</script>")[0].replace(/^import[\s\S]*? from ["'][^"']+["'];?\n/gm, "")
	const values = {
		...Vue, watch: () => {}, onBeforeUnmount: () => {}, onBeforeRouteLeave: () => {}, onBeforeRouteUpdate: () => {},
		defineProps: () => ({ boxStickerPrintId: "", newRouteName: "box-new", viewRouteName: "box" }),
		useRoute: () => ({ query: { duplicate_from: "BSP-1" } }), useRouter: () => ({ push() {}, replace() {} }),
		usePageTitle: () => {}, useDuplicateAction: () => ({ value: null }),
		takeNewDocumentDefaults: () => ({}), withNewDocumentDefaults,
		window: { addEventListener() {}, removeEventListener() {} },
		...bindings,
	}
	return new Function(...Object.keys(values), `${script}\nreturn { load, form, rows, dirty, documentActions }`)(...Object.values(values))
}

test("Duplicate copies the header and the typed MRP and quantities but not the printed quantities", async () => {
	const sources = []
	const box = page({
		loadDuplicateValues: async (doctype, route) => {
			assert.deepEqual([doctype, route.query.duplicate_from], ["SD YRP Box Sticker Print", "BSP-1"])
			return { lot: "LOT-1", fg_item: "FG-1", size: "Kids", use_item_name: 1, print_format: "ZPL-1", against: "YRP Work Order", against_id: "WO-1",
				box_sticker_print_details: [{ size: "IAV-M", mrp: 249, quantity: 30, printed_quantity: 12, allow_excess_percentage: 10 }] }
		},
		getBoxStickerEditor: async (name) => { assert.equal(name, ""); return { permissions: { can_create: true }, defaults: { lot: null, fg_item: null, size: null, use_item_name: 0, print_format: null, rows: [] }, record: null } },
		previewBoxStickerSource: async (...args) => { sources.push(args); return { rows: [{ size: "M", mrp: 249, quantity: 30, printed_quantity: 0, allow_excess_percentage: 10 }] } },
	})
	await box.load()
	assert.deepEqual({ ...box.form }, { lot: "LOT-1", fg_item: "FG-1", size: "Kids", use_item_name: 1, print_format: "ZPL-1" })
	assert.deepEqual(sources[0].slice(0, 2), ["LOT-1", "FG-1"])
	assert.deepEqual(sources[0][2].rows, [{ size: "IAV-M", mrp: 249, quantity: 30, allow_excess_percentage: 10 }])
	assert.equal(box.rows.value[0].printed_quantity, 0)
	assert.equal(box.dirty.value, true)
	assert.deepEqual(box.documentActions().filter(Boolean).map((action) => [action.key, action.primary]), [["save", true]])
})
