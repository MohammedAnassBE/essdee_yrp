import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const duplicate = await import("../src/composables/useDuplicateAction.js")
const accountsViews = await import("../src/departments/accounts/accountsViews.js")
const hrViews = await import("../src/departments/hr/hrViews.js")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const stub = (tag) => (props, { slots }) => Vue.h(tag, props, slots?.default?.())
const helpers = new Proxy({}, { get: () => () => ({}) })
const workspaceStub = (props, { slots }) => Vue.h("workspace", props, props.loading ? [] : [slots["header-actions"]?.()])

// Stub every import of the page except Vue, the duplicate composable and the given overrides.
function page(path, overrides) {
	const filename = resolve(`frontend/src/departments/${path}.vue`)
	const specifiers = [...readFileSync(filename, "utf8").matchAll(/from\s+["']([^"']+)["']/g)].map((match) => match[1])
	const modules = Object.fromEntries(specifiers.map((specifier) => [specifier, specifier.endsWith(".vue") || specifier.startsWith("primevue/") ? stub(specifier.split("/").pop()) : helpers]))
	return loadComponent(filename, {
		...modules,
		vue: Vue,
		"primevue/usetoast": { useToast: () => ({ add() {} }) },
		"../fabric-store/FabricDocumentWorkspace.vue": workspaceStub,
		"../../components/documents/DocumentActionStrip.vue": (props) => Vue.h("action-strip", props),
		"../../composables/useDuplicateAction.js": duplicate,
		...overrides,
	})
}

function router(route) {
	const pushes = []
	return { pushes, module: { useRoute: () => route, useRouter: () => ({ push: async (target) => pushes.push(target), replace: async () => {} }), onBeforeRouteLeave() {}, onBeforeRouteUpdate() {} } }
}

async function viewActions(path, props, overrides, routeParams) {
	const nav = router(Vue.reactive({ params: routeParams, query: {}, fullPath: "/view" }))
	const root = mountComponent(page(path, { "vue-router": nav.module, ...overrides }), props)
	await tick(); await tick()
	const actions = () => findNodes(root, (node) => node.type === "action-strip")[0]?.props.actions || []
	return { actions, duplicateAction: () => actions().find((action) => action.key === "duplicate"), pushes: nav.pushes }
}

const productionOrder = (canCreate) => ({ "../../api/sales.js": { getProductionOrderWorkspace: async () => ({ record: { name: "PPO-1" }, permissions: { can_create: canCreate }, capabilities: {} }) } })

test("Production Order Duplicate is menu-only, gated on create and opens the route's new editor", async () => {
	const view = await viewActions("sales/ProductionOrder", { editRouteName: "merch-production-order-edit" }, productionOrder(true), { productionOrderId: "PPO-1" })
	const action = view.duplicateAction()
	assert.deepEqual({ label: action.label, menuOnly: action.menuOnly, icon: action.icon }, { label: "Duplicate", menuOnly: true, icon: "pi pi-clone" })
	await action.command()
	assert.deepEqual(view.pushes, [{ name: "merch-production-order-new", query: { duplicate_from: "PPO-1" } }])
	const denied = await viewActions("sales/ProductionOrder", {}, productionOrder(false), { productionOrderId: "PPO-1" })
	assert.equal(denied.duplicateAction(), undefined)
})

test("Purchase Invoice and Bill Tracking Duplicate open their department's new editor", async () => {
	const invoice = await viewActions("accounts/PurchaseInvoice", { purchaseInvoiceId: "PI-1" }, {
		"./accountsViews.js": accountsViews,
		"../../api/accounts.js": { getPurchaseInvoiceWorkspace: async () => ({ record: { name: "PI-1" }, permissions: { can_create: true }, capabilities: {} }) },
	}, { purchaseInvoiceId: "PI-1" })
	await invoice.duplicateAction().command()
	assert.deepEqual(invoice.pushes, [{ name: "accounts-purchase-invoice-new", query: { duplicate_from: "PI-1" } }])
	const bill = await viewActions("hr/BillTracking", { billTrackingId: "BT-1", editRouteName: "merch-bill-tracking-edit" }, {
		"./hrViews.js": hrViews,
		"../../api/hr.js": { getBillTrackingWorkspace: async () => ({ record: { name: "BT-1" }, permissions: { can_create: true }, capabilities: {} }) },
	}, { billTrackingId: "BT-1" })
	await bill.duplicateAction().command()
	assert.deepEqual(bill.pushes, [{ name: "merch-bill-tracking-new", query: { duplicate_from: "BT-1" } }])
})

test("new editors pass duplicate_from to their builder only for new documents", async () => {
	const calls = []
	const editor = page("sales/ProductionOrderEditor", {
		"../../api/sales.js": { getProductionOrderEditor: async (...args) => { calls.push(args); return {} }, saveProductionOrder() {} },
		"./productionOrderOptions.js": { productionOrderItemFilters: {} },
		"./productionOrderSaveBlockers.js": { productionOrderSaveBlockers: () => [], productionOrderDeliveryWarning: () => "" },
	})
	mountComponent(editor, { duplicateFrom: "PPO-1" })
	mountComponent(editor, { name: "PPO-2", duplicateFrom: "PPO-1" })
	await tick()
	assert.deepEqual(calls, [[null, null, "PPO-1"], ["PPO-2", null, null]])

	const billCalls = []
	const nav = router(Vue.reactive({ params: {}, query: { duplicate_from: "BT-1" } }))
	const previous = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {} }
	try {
		mountComponent(page("hr/BillTrackingEditorPage", {
			"vue-router": nav.module,
			"../../components/documents/DocumentFieldGroupGrid.vue": () => null,
			"../../api/hr.js": { getBillTrackingEditor: async (...args) => { billCalls.push(args); return { values: { supplier: "SUP-1" } } }, saveBillTracking() {} },
		}), {})
		await tick()
	} finally { globalThis.window = previous }
	assert.deepEqual(billCalls, [[null, "BT-1"]])
})

test("Debit Duplicate opens an unsaved New Debit form with only the request fields copied", async () => {
	const debitFields = (await import("../src/config/fields/debit.js")).default
	const loads = []
	const debits = (route) => {
		const nav = router(Vue.reactive(route))
		const root = mountComponent(page("accounts/Debits", {
			"vue-router": nav.module,
			"../../config/fields/debit.js": debitFields,
			"../../router/departmentLock.js": { isOutsideLayout: () => false, getHomePath: () => "/" },
			"../../api/frappe.js": { getDoc: async () => ({ name: "DEBIT-1", work_order: "WO-1" }), getMeta: async () => [] },
			"../../composables/useDocumentPermissions.js": { useDocumentPermissions: () => Vue.ref({ create: 1 }) },
			"../../composables/useDuplicateAction.js": { loadDuplicateValues: async (doctype) => { loads.push(doctype); return { doctype, work_order: "WO-1", debit_value: 40, reason: null, status: "Approved", approved_by: "boss@example.com" } } },
			"../../components/common/FormView.vue": (props) => Vue.h("form-view", props),
			"primevue/dialog": (props, { slots }) => props.visible ? Vue.h("dialog", props, slots.default?.()) : null,
			"primevue/button": (props) => Vue.h("button", props, props.label),
		}), {})
		return { root, pushes: nav.pushes }
	}
	const view = debits({ params: { debitId: "DEBIT-1" }, query: {} })
	await tick()
	findNodes(view.root, (node) => node.type === "button" && node.props.label === "Duplicate")[0].props.onClick()
	assert.deepEqual(view.pushes, [{ path: "/accounts/debits", query: { duplicate_from: "DEBIT-1" } }])
	const copy = debits({ params: {}, query: { duplicate_from: "DEBIT-1" } })
	await tick(); await tick()
	assert.deepEqual(loads, ["YRP Debit"])
	const form = findNodes(copy.root, (node) => node.type === "form-view")[0].props
	assert.deepEqual({ doctype: form.doctype, name: form.name, initialValues: form["initial-values"] }, { doctype: "YRP Debit", name: undefined, initialValues: { work_order: "WO-1", debit_value: 40 } })
	form.onSaved({ name: "DEBIT-2" })
	assert.deepEqual(copy.pushes, ["/accounts/debits/DEBIT-2"])
})
