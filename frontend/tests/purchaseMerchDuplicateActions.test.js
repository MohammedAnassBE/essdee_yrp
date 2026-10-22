import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const duplicate = await import("../src/composables/useDuplicateAction.js")
const purchaseViews = await import("../src/departments/purchase/purchaseViews.js")
const merchViews = await import("../src/departments/merch/merchViews.js")
const purchaseApi = await import("../src/api/purchase.js")
const merchApi = await import("../src/api/merch.js")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const stub = (tag) => (props, { slots }) => Vue.h(tag, props, slots?.default?.())
const helpers = new Proxy({}, { get: () => () => ({}) })
const workspaceStub = (props, { slots }) => Vue.h("workspace", props, props.loading ? [] : [slots["header-actions"]?.()])
const actionStrip = (props) => Vue.h("action-strip", props)

function page(path, overrides) {
	const filename = resolve(`frontend/src/departments/${path}.vue`)
	const specifiers = [...readFileSync(filename, "utf8").matchAll(/from\s+["']([^"']+)["']/g)].map((match) => match[1])
	const modules = Object.fromEntries(specifiers.map((specifier) => [specifier, specifier.endsWith(".vue") || specifier.startsWith("primevue/") ? stub(specifier.split("/").pop()) : helpers]))
	for (const specifier of specifiers) {
		if (specifier.endsWith("composables/useDuplicateAction.js")) modules[specifier] = duplicate
		if (specifier.endsWith("FabricDocumentWorkspace.vue")) modules[specifier] = workspaceStub
		if (specifier.endsWith("documents/DocumentActionStrip.vue")) modules[specifier] = actionStrip
	}
	return loadComponent(filename, { ...modules, vue: Vue, "primevue/usetoast": { useToast: () => ({ add() {} }) }, ...overrides })
}

async function mountActions(path, overrides, props) {
	const pushes = []
	const router = { push: (location) => { pushes.push(location); return Promise.resolve() }, replace: () => Promise.resolve() }
	const root = mountComponent(page(path, { "vue-router": { useRouter: () => router, useRoute: () => ({ query: {}, hash: "" }), RouterLink: stub("a") }, ...overrides }), props)
	await tick()
	await tick()
	const actions = findNodes(root, (node) => node.type === "action-strip").flatMap((node) => node.props.actions || [])
	return { actions, pushes }
}

function duplicateOf(actions) {
	return actions.find((action) => action.key === "duplicate")
}

const itemPrice = (canCreate) => ({
	record: { name: "ITP-1", docstatus: 1, workflow_state: "Approved" }, tiers: [], actions: [],
	can_edit: true, can_delete: false, permissions: { can_create: canCreate },
})

test("Item Price page offers a menu-only Duplicate that opens the new editor", async () => {
	const view = await mountActions("purchase/ItemPricePage", {
		"../../api/purchase.js": { getItemPriceWorkspace: async () => itemPrice(true) },
		"./purchaseViews.js": purchaseViews,
	}, { priceId: "ITP-1" })
	const action = duplicateOf(view.actions)
	assert.ok(action, "Duplicate action is missing")
	assert.equal(action.menuOnly, true)
	action.command()
	assert.deepEqual(view.pushes, [{ name: "purchase-item-price-new", query: { duplicate_from: "ITP-1" } }])
})

test("Item Price page hides Duplicate without create permission", async () => {
	const view = await mountActions("purchase/ItemPricePage", {
		"../../api/purchase.js": { getItemPriceWorkspace: async () => itemPrice(false) },
		"./purchaseViews.js": purchaseViews,
	}, { priceId: "ITP-1" })
	assert.deepEqual(view.actions.map((action) => action.key), ["edit"])
})

test("Process Cost page offers Duplicate to users who can create", async () => {
	const view = await mountActions("merch/process-cost/ProcessCostPage", {
		"../../../api/merch.js": { getProcessCostWorkspace: async () => ({ record: { name: "PC-1" }, permissions: { can_create: true }, actions: [] }) },
		"../merchViews.js": merchViews,
		"./processCostViews.js": { ...helpers, processCostActions: () => [], PROCESS_COST_TABS: [], PROCESS_COST_SECTIONS: [], PROCESS_COST_DOCUMENT_SECTIONS: [] },
	}, { processCostId: "PC-1" })
	duplicateOf(view.actions).command()
	assert.deepEqual(view.pushes, [{ name: "merch-process-cost-new", query: { duplicate_from: "PC-1" } }])
})

function withFetch(run) {
	const previousWindow = globalThis.window
	const previousFetch = globalThis.fetch
	const requests = []
	globalThis.window = { csrf_token: "test-csrf" }
	globalThis.fetch = async (url, options) => {
		requests.push({ url, body: JSON.parse(options.body) })
		return { ok: true, status: 200, json: async () => ({ message: {} }) }
	}
	return run(requests).finally(() => { globalThis.window = previousWindow; globalThis.fetch = previousFetch })
}

test("editor loaders send duplicate_from to their backend builders", () => withFetch(async (requests) => {
	await purchaseApi.getItemPriceEditor(null, null, "ITP-1")
	await purchaseApi.getItemEditor(null, "ITEM-1")
	await purchaseApi.getLotForm(null, "LOT-1")
	await merchApi.getMerchLotEditor(null, "LOT-1")
	await merchApi.getIpdEditor(null, "IPD-1")
	await merchApi.saveIpd({}, { duplicateFrom: "IPD-1" })
	await merchApi.getProcessCostEditor(null, null, "PC-1")
	assert.deepEqual(requests.map((request) => request.body.duplicate_from), ["ITP-1", "ITEM-1", "LOT-1", "LOT-1", "IPD-1", "IPD-1", "PC-1"])
}))

test("Item Price editor reloads when the duplicate source changes", () => {
	const key = (duplicateFrom) => purchaseViews.itemPriceEditorRequestKey({ routeName: "purchase-item-price-new", duplicateFrom })
	assert.notEqual(key("ITP-1"), key("ITP-2"))
	assert.equal(JSON.parse(purchaseViews.itemPriceEditorRequestKey({ name: "ITP-1", duplicateFrom: "ITP-2" })).duplicateFrom, "")
})

test("Lot, Item, IPD and Process Cost pages and editors wire Duplicate", () => {
	const source = (path) => readFileSync(resolve(`frontend/src/departments/${path}`), "utf8")
	for (const [path, route] of [["purchase/lot/LotPage.vue", "PURCHASE_ROUTES.lotNew"], ["merch/lot/MerchLotPage.vue", "MERCH_ROUTES.lotNew"], ["purchase/ItemPage.vue", "PURCHASE_ROUTES.itemNew"], ["merch/ipd/IpdPage.vue", "MERCH_ROUTES.ipdNew"]]) {
		assert.match(source(path), new RegExp(`useDuplicateAction\\(\\{[\\s\\S]*?newRouteName: ${route.replace(".", "\\.")}`), path)
	}
	for (const path of ["purchase/lot/useLotEditor.js", "merch/lot/useMerchLotEditor.js", "purchase/ItemEditorPage.vue", "purchase/ItemPriceEditor.vue", "merch/ipd/useIpdEditor.js", "merch/process-cost/ProcessCostEditor.vue"]) {
		assert.match(source(path), /duplicate_from/, path)
	}
})
