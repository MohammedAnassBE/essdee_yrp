import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const hrViews = await import("../src/departments/hr/hrViews.js")
const duplicate = await import("../src/composables/useDuplicateAction.js")
const dateFormat = await import("../src/utils/dateFormat.js")
const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
const stub = (tag) => (props, { slots }) => Vue.h(tag, props, slots?.default?.())
const helpers = new Proxy({}, { get: () => () => ({}) })
const router = { push: async () => {}, replace: async () => {} }
const routerModule = (route) => ({ useRoute: () => route, useRouter: () => router, onBeforeRouteLeave() {}, onBeforeRouteUpdate() {} })

function stubModules(filename) {
	const specifiers = [...readFileSync(filename, "utf8").matchAll(/from\s+["']([^"']+)["']/g)].map((match) => match[1])
	return Object.fromEntries(specifiers.map((specifier) => [specifier, specifier.endsWith(".vue") || specifier.startsWith("primevue/") ? stub(specifier.split("/").pop()) : helpers]))
}

function textOf(node) {
	if (node == null || typeof node === "boolean") return ""
	if (typeof node === "string" || typeof node === "number") return String(node)
	return [node.text, ...node.children.map(textOf)].join(" ")
}

const detail = (fieldname, value, fieldtype = "Data") => ({ fieldname, label: fieldname, fieldtype, value })

async function mountView(workspace) {
	const filename = resolve("frontend/src/departments/hr/BillTracking.vue")
	const workspaceStub = (props, { slots }) => Vue.h("workspace", props, [slots.header?.({ record: props.workspace.record || {}, headingId: "h" }), slots.fields?.()])
	const component = loadComponent(filename, {
		...stubModules(filename),
		vue: Vue,
		"../fabric-store/FabricDocumentWorkspace.vue": workspaceStub,
		"../../components/documents/DocumentOverview.vue": (props) => Vue.h("overview", props),
		"../../components/common/DocumentLink.vue": (props) => Vue.h("link", props, props.label),
		"../../composables/useDuplicateAction.js": duplicate,
		"./hrViews.js": hrViews,
		"../../utils/dateFormat.js": dateFormat,
		"../../api/hr.js": { getBillTrackingWorkspace: async () => workspace },
		"vue-router": routerModule(Vue.reactive({ params: { billTrackingId: "VBT-1" }, query: {}, fullPath: "/view" })),
	})
	const root = mountComponent(component, { billTrackingId: "VBT-1" })
	await tick(); await tick()
	return root
}

test("Bill Tracking view shows GSTIN and Bill No in the header and every Desk section", async () => {
	const root = await mountView({
		record: { name: "VBT-1", supplier: "Sun Knit", gstin: "33CQXPP8124R1ZP", bill_no: "335", bill_date: "2026-09-19", invoice_value: 54656 },
		details: [detail("gstin", "33CQXPP8124R1ZP"), detail("department", null), detail("cancel_reason", ""), detail("amended_from", "VBT-0")],
		history: [{ action: "Open", assigned_by: "a@example.test", assigned_on: "2026-09-20 14:05:09.123456" }],
		permissions: {},
		capabilities: {},
	})
	const text = textOf(root)
	assert.ok(!text.includes("2026-09-19"), "bill date must not render as ISO")
	assert.ok(!text.includes("2026 · 14"), "datetimes must use a single space separator")
	for (const value of ["33CQXPP8124R1ZP", "335", "19-09-2026", "20-09-2026 14:05", "GSTIN / UIN", "Bill No", "Bill Tracking History", "Assigned By"]) {
		assert.ok(text.includes(value), `${value} should render`)
	}
	const overview = findNodes(root, (node) => node.type === "overview")[0]
	assert.equal(overview.props["include-empty"], "")
	assert.deepEqual(overview.props.definitions.map((group) => group.label), ["Vendor Details", "Delivery Details", "Status"])
	const fields = overview.props.definitions.flatMap((group) => group.fields)
	for (const fieldname of ["supplier", "gstin", "pan", "bill_no", "bill_date", "invoice_value", "department", "purchase_invoice", "erp_purchase_invoice", "received_date", "received_via", "receive_comment", "delivery_mob_no", "delivery_person", "assigned_to", "form_status", "cancel_reason", "amended_from"]) {
		assert.ok(fields.includes(fieldname), `${fieldname} should have a section`)
	}
	assert.deepEqual(overview.props.fields.map((field) => field.fieldname), ["gstin", "department", "amended_from"])
})

test("Bill Tracking list shows GSTIN beside Bill No", () => {
	const columns = hrViews.BILL_TRACKING_LIST_COLUMNS
	assert.deepEqual(columns.slice(0, 3), ["supplier", "gstin", "bill_no"])
	assert.ok(columns.includes("received_date"))
})

async function mountEditor(values, taxIds) {
	globalThis.window ??= { addEventListener() {}, removeEventListener() {} }
	const filename = resolve("frontend/src/departments/hr/BillTrackingEditorPage.vue")
	const calls = []
	const groupGrid = (props, { slots }) => Vue.h("groups", props, props.groups.map((group) => slots.default({ group })))
	const component = loadComponent(filename, {
		...stubModules(filename),
		vue: Vue,
		"primevue/usetoast": { useToast: () => ({ add() {} }) },
		"../../components/documents/DocumentFieldGroupGrid.vue": groupGrid,
		"../../components/common/FormField.vue": (props) => Vue.h("form-field", props),
		"../../api/hr.js": {
			getBillTrackingEditor: async () => ({ values, schema: {}, received_via_options: ["HO"] }),
			getSupplierTaxIds: async (supplier) => { calls.push(supplier); return taxIds },
			saveBillTracking: async () => ({}),
		},
		"vue-router": routerModule(Vue.reactive({ params: {}, query: {}, fullPath: "/new" })),
	})
	const root = mountComponent(component, {})
	await tick(); await tick()
	return { root, calls }
}

test("Bill Tracking editor edits GSTIN, PAN and Department and fetches tax IDs from the supplier", async () => {
	const values = { supplier: "", gstin: "", pan: "", bill_no: "", bill_date: "", invoice_value: "", department: "", received_date: "", received_via: "", receive_comment: "", delivery_mob_no: "" }
	const { root, calls } = await mountEditor(values, { gstin: "33ABCDE1234F1Z5", pan: "ABCDE1234F" })
	const fields = () => findNodes(root, (node) => node.type === "form-field")
	assert.deepEqual(fields().map((node) => node.props.field.fieldname), ["supplier", "bill_no", "gstin", "bill_date", "pan", "invoice_value", "department", "received_date", "received_via", "receive_comment"])
	fields()[0].props["onUpdate:modelValue"]("Sun Knit")
	await tick(); await tick()
	assert.deepEqual(calls, ["Sun Knit"])
	const byName = Object.fromEntries(fields().map((node) => [node.props.field.fieldname, node.props.modelValue]))
	assert.equal(byName.gstin, "33ABCDE1234F1Z5")
	assert.equal(byName.pan, "ABCDE1234F")
})

test("Bill Tracking editor hides fields the user cannot read", async () => {
	const { root } = await mountEditor({ supplier: "", bill_no: "", bill_date: "", invoice_value: "", received_date: "", received_via: "", receive_comment: "", delivery_mob_no: "" }, {})
	const names = findNodes(root, (node) => node.type === "form-field").map((node) => node.props.field.fieldname)
	assert.ok(!names.includes("gstin") && !names.includes("department"))
})
