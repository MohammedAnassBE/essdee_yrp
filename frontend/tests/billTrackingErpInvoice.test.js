import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const hrViews = await import("../src/departments/hr/hrViews.js")
const duplicate = await import("../src/composables/useDuplicateAction.js")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const stub = (tag) => (props, { slots }) => Vue.h(tag, props, slots?.default?.())
const helpers = new Proxy({}, { get: () => () => ({}) })
const workspaceStub = (props, { slots }) => Vue.h("workspace", props, props.loading ? [] : [slots["header-actions"]?.()])

async function billTrackingActions(capabilities) {
	const filename = resolve("frontend/src/departments/hr/BillTracking.vue")
	const specifiers = [...readFileSync(filename, "utf8").matchAll(/from\s+["']([^"']+)["']/g)].map((match) => match[1])
	const modules = Object.fromEntries(specifiers.map((specifier) => [specifier, specifier.endsWith(".vue") || specifier.startsWith("primevue/") ? stub(specifier.split("/").pop()) : helpers]))
	const route = Vue.reactive({ params: { billTrackingId: "BT/1" }, query: {}, fullPath: "/view" })
	const component = loadComponent(filename, {
		...modules,
		vue: Vue,
		"primevue/usetoast": { useToast: () => ({ add() {} }) },
		"../fabric-store/FabricDocumentWorkspace.vue": workspaceStub,
		"../../components/documents/DocumentActionStrip.vue": (props) => Vue.h("action-strip", props),
		"../../composables/useDuplicateAction.js": duplicate,
		"./hrViews.js": hrViews,
		"../../api/hr.js": { getBillTrackingWorkspace: async () => ({ record: { name: "BT/1" }, permissions: {}, capabilities }) },
		"vue-router": { useRoute: () => route, useRouter: () => ({ push: async () => {}, replace: async () => {} }), onBeforeRouteLeave() {}, onBeforeRouteUpdate() {} },
	})
	const root = mountComponent(component, { billTrackingId: "BT/1" })
	await tick(); await tick()
	return findNodes(root, (node) => node.type === "action-strip")[0]?.props.actions || []
}

const allowed = (label) => ({ allowed: true, label })

test("Create ERP Purchase Invoice opens Desk's new Purchase Invoice linked to the bill", async () => {
	const actions = await billTrackingActions({
		create_purchase_invoice: allowed("Create YRP Purchase Invoice"),
		create_erp_purchase_invoice: allowed("Create ERP Purchase Invoice"),
	})
	const action = actions.find((entry) => entry.key === "create_erp_purchase_invoice")
	assert.equal(action.label, "Create ERP Purchase Invoice")
	assert.ok(actions.some((entry) => entry.key === "create_purchase_invoice"))

	const opened = []
	const previous = globalThis.window
	globalThis.window = { open: (...args) => opened.push(args) }
	try {
		await action.command()
	} finally {
		globalThis.window = previous
	}
	assert.deepEqual(opened, [["/app/purchase-invoice/new?vendor_bill_tracking=BT%2F1", "_blank", "noopener"]])
})

test("Create ERP Purchase Invoice is hidden when the server does not allow it", async () => {
	const actions = await billTrackingActions({
		create_purchase_invoice: allowed("Create YRP Purchase Invoice"),
		create_erp_purchase_invoice: { allowed: false, label: "Create ERP Purchase Invoice" },
	})
	assert.equal(actions.find((entry) => entry.key === "create_erp_purchase_invoice"), undefined)
})
