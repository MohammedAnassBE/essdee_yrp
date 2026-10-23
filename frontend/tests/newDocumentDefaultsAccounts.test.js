import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

const defaults = await import("../src/utils/newDocumentDefaults.js")
const accountsViews = await import("../src/departments/accounts/accountsViews.js")
const qualityViews = await import("../src/departments/quality/qualityViews.js")
const inspectionFields = await import("../src/departments/quality/inspectionFields.js")
const tick = async () => { for (let index = 0; index < 4; index += 1) { await new Promise((done) => setImmediate(done)); await Vue.nextTick() } }
const stub = (tag) => (props, { slots }) => Vue.h(tag, props, slots?.default?.())
const helpers = new Proxy({}, { get: () => () => ({}) })
const nodes = (root, type) => findNodes(root, (node) => node.type === type)
const LIST_PATH = "/list?filtered=1"

function page(path, overrides) {
	const filename = resolve(`frontend/src/departments/${path}.vue`)
	const specifiers = [...readFileSync(filename, "utf8").matchAll(/from\s+["']([^"']+)["']/g)].map((match) => match[1])
	const modules = Object.fromEntries(specifiers.map((specifier) => [specifier, specifier.endsWith(".vue") || specifier.startsWith("primevue/") ? stub(specifier.split("/").pop().replace(".vue", "").toLowerCase()) : helpers]))
	return loadComponent(filename, {
		...modules,
		vue: Vue,
		"primevue/usetoast": { useToast: () => ({ add() {} }) },
		"../../utils/newDocumentDefaults.js": defaults,
		...overrides,
	})
}

function routerModule(query = {}) {
	const route = Vue.reactive({ params: {}, query, fullPath: "/new" })
	return { useRoute: () => route, useRouter: () => ({ push: async () => {}, replace: async () => {} }), onBeforeRouteLeave() {}, onBeforeRouteUpdate() {} }
}

async function withListHistory(run) {
	const previous = globalThis.window
	globalThis.window = { addEventListener() {}, removeEventListener() {}, history: { state: { back: LIST_PATH, current: "/new" } }, frappe: {} }
	try { return await run() } finally { globalThis.window = previous }
}

test("a new Production Order takes the list's filter values, loads a defaulted Item and keeps server values", async () => {
	const calls = []
	const editor = page("sales/ProductionOrderEditor", {
		"../../api/sales.js": { getProductionOrderEditor: async (...args) => { calls.push(args); return { fields: [{ fieldname: "production_term", value: "Server Term" }] } }, saveProductionOrder() {} },
		"./productionOrderOptions.js": { productionOrderItemFilters: {} },
		"./productionOrderSaveBlockers.js": { productionOrderSaveBlockers: () => [], productionOrderDeliveryWarning: () => "" },
	})
	const root = await withListHistory(async () => {
		defaults.stageNewDocumentDefaults("YRP Production Order", { item: "STYLE-1", production_term: "Filter Term", comments: "x", not_on_form: "y" }, LIST_PATH)
		const mounted = mountComponent(editor, {})
		await tick()
		return mounted
	})
	const value = (label) => nodes(root, "linkfield").find((node) => node.props.label?.startsWith(label))?.props.modelValue
	assert.equal(value("Item"), "STYLE-1")
	assert.equal(value("Production Term"), "Server Term")
	assert.deepEqual(calls, [[null, null, null], [null, { item: "STYLE-1" }]])
})

test("a duplicated Production Order clears the staged values without applying them", async () => {
	const editor = page("sales/ProductionOrderEditor", {
		"../../api/sales.js": { getProductionOrderEditor: async () => ({}), saveProductionOrder() {} },
		"./productionOrderOptions.js": { productionOrderItemFilters: {} },
		"./productionOrderSaveBlockers.js": { productionOrderSaveBlockers: () => [], productionOrderDeliveryWarning: () => "" },
	})
	const root = await withListHistory(async () => {
		defaults.stageNewDocumentDefaults("YRP Production Order", { item: "STYLE-1" }, LIST_PATH)
		const mounted = mountComponent(editor, { duplicateFrom: "PPO-1" })
		await tick()
		return mounted
	})
	assert.equal(nodes(root, "linkfield").find((node) => node.props.label?.startsWith("Item")).props.modelValue, "")
	assert.deepEqual(defaults.takeNewDocumentDefaults("YRP Production Order", { back: LIST_PATH }), {})
})

test("a new Bill Tracking fills empty fields from the list filters and keeps editor values", async () => {
	const grid = (props, { slots }) => Vue.h("grid", null, props.groups.flatMap((group) => slots.default?.({ group }) || []))
	const values = { supplier: "", bill_no: "", department: "Server Dept", received_date: "", gstin: "", pan: "", bill_date: "", invoice_value: "", received_via: "", receive_comment: "" }
	const root = await withListHistory(async () => {
		defaults.stageNewDocumentDefaults("YRP Bill Tracking", { supplier: "SUP-1", department: "Filter Dept", bill_no: "B-7" }, LIST_PATH)
		const mounted = mountComponent(page("hr/BillTrackingEditorPage", {
			"vue-router": routerModule(),
			"../../components/documents/DocumentFieldGroupGrid.vue": grid,
			"../../components/common/FormField.vue": (props) => Vue.h("field", props),
			"../../api/hr.js": { getBillTrackingEditor: async () => ({ values }), getSupplierTaxIds: async () => ({ gstin: "GST-1", pan: "PAN-1" }), saveBillTracking() {} },
		}), {})
		await tick()
		return mounted
	})
	const value = (fieldname) => nodes(root, "field").find((node) => node.props.field.fieldname === fieldname)?.props.modelValue
	assert.equal(value("supplier"), "SUP-1")
	assert.equal(value("bill_no"), "B-7")
	assert.equal(value("department"), "Server Dept")
})

test("a new Purchase Invoice takes filter values; a Bill Tracking source skips them", async () => {
	const invoice = async (query) => withListHistory(async () => {
		defaults.stageNewDocumentDefaults("YRP Purchase Invoice", { supplier: "SUP-1", remarks: "Filter remark", against: "Filter Against" }, LIST_PATH)
		const root = mountComponent(page("accounts/PurchaseInvoiceEditorPage", {
			"vue-router": routerModule(query),
			"./accountsViews.js": accountsViews,
			"../../api/accounts.js": { getPurchaseInvoiceEditor: async () => ({ values: { against: "Server Against" } }), savePurchaseInvoice() {}, fetchExpenseHeads() {}, fetchGrnDetails() {} },
			"./components/PurchaseInvoiceEditorBody.vue": (props) => Vue.h("body", props),
		}), {})
		await tick()
		return nodes(root, "body")[0].props.form
	})
	const fresh = await invoice({})
	assert.equal(fresh.supplier, "SUP-1")
	assert.equal(fresh.remarks, "Filter remark")
	assert.equal(fresh.against, "Server Against")
	const sourced = await invoice({ bill_tracking: "BT-1" })
	assert.equal(sourced.supplier, "")
})

test("a new Quality Inspection takes the list's Work Order and type and loads that Work Order", async () => {
	const detailCalls = []
	const root = await withListHistory(async () => {
		defaults.stageNewDocumentDefaults(qualityViews.INSPECTION_DOCTYPE, { against_id: "WO-9", inspection_type: "Final", is_third_party: 1, checking_level: "Filter Level" }, LIST_PATH)
		const mounted = mountComponent(page("quality/QualityInspectionEditorPage", {
			"vue-router": routerModule(),
			"./qualityViews.js": qualityViews,
			"./inspectionFields.js": inspectionFields,
			"../../utils/documentOverview.js": { formatDocumentOverviewValue: (value) => value },
			"../../components/common/FormField.vue": (props) => Vue.h("field", props),
			"../../api/quality.js": {
				getNewInspectionDefaults: async () => ({ checking_level: "Server Level" }),
				getInspectionAgainstDetails: async (name) => { detailCalls.push(name); return { item: "STYLE", lot: "LOT" } },
				getInspectionAqlLimits: async () => ({}), getInspectionWorkspace() {}, saveInspection() {},
			},
		}), {})
		await tick()
		return mounted
	})
	const value = (fieldname) => nodes(root, "field").find((node) => node.props.field?.fieldname === fieldname)?.props.modelValue
	assert.deepEqual(detailCalls, ["WO-9"])
	assert.equal(value("inspection_type"), "Final")
	assert.equal(value("checking_level"), "Server Level")
	assert.equal(Number(value("is_third_party")), 1)
})
