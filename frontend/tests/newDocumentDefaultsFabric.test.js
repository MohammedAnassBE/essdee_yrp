import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { Vue } from "../../scripts/helpers/vue_renderer.mjs"
import { createPurchaseOrderDraftRevision, createPurchaseOrderPreviewController, loadPurchaseOrderGroups } from "../src/utils/purchaseOrder.js"
import { defaultOption } from "../src/utils/supplierDefaults.js"
import { stageNewDocumentDefaults, takeNewDocumentDefaults, withNewDocumentDefaults } from "../src/utils/newDocumentDefaults.js"

const LIST_PATH = "/fabric-store/list"
const settle = () => new Promise((done) => setImmediate(done))
const noop = () => ({})
const defaultsApi = { takeNewDocumentDefaults, withNewDocumentDefaults }

/** Runs a component's `<script setup>` with its imports replaced by `bindings`; unknown names resolve to no-ops. */
function setup(path, bindings, exported) {
	const source = readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")
	const script = source.split("<script setup>")[1].split("</script>")[0].replace(/^import[\s\S]*? from ["'][^"']+["'];?\n/gm, "")
	const all = { ...Vue, onMounted: () => {}, onBeforeUnmount: () => {}, defineEmits: () => () => {}, onBeforeRouteLeave: () => {}, useToast: () => ({ add() {} }), ...defaultsApi, ...bindings }
	const scope = new Proxy({}, {
		has: (_, key) => typeof key === "string",
		get: (_, key) => key in all ? all[key] : key in globalThis ? globalThis[key] : noop,
	})
	return new Function("scope", `with (scope) {\n${script}\nreturn { ${exported} }\n}`)(scope)
}

function fromList(doctype, values) {
	globalThis.window = { history: { state: { back: LIST_PATH, current: "/new" } }, addEventListener() {}, removeEventListener() {} }
	stageNewDocumentDefaults(doctype, values, LIST_PATH)
}

test("a new Delivery Challan loads a filtered Work Order as its source and prefills the other filters", () => {
	fromList("YRP Delivery Challan", { work_order: "WO-1", lot: "LOT-1" })
	const page = setup("FabricDeliveryChallan.vue", {
		defineProps: () => ({ sourceContext: {}, name: "" }),
		useRoute: () => ({ params: {}, query: {} }), useRouter: noop,
	}, "resolvedSourceContext, newDefaults")
	assert.deepEqual(page.resolvedSourceContext.value, { work_order: "WO-1" })
	assert.deepEqual(page.newDefaults, { lot: "LOT-1" })
})

test("a duplicated Delivery Challan clears the staged filters without applying them", () => {
	fromList("YRP Delivery Challan", { lot: "LOT-1" })
	const page = setup("FabricDeliveryChallan.vue", {
		defineProps: () => ({ sourceContext: {}, name: "" }),
		useRoute: () => ({ params: {}, query: { duplicate_from: "DC-1" } }), useRouter: noop,
	}, "resolvedSourceContext, newDefaults")
	assert.deepEqual(page.newDefaults, {})
	assert.deepEqual(page.resolvedSourceContext.value, { duplicate_from: "DC-1" })
	assert.deepEqual(takeNewDocumentDefaults("YRP Delivery Challan"), {})
})

test("the Delivery Challan draft takes filter values into empty fields only", () => {
	const props = { name: "", sourceContext: {}, newDefaults: { lot: "LOT-1", process_name: "Filter Process", unknown_field: "x" } }
	const state = setup("fabric-store/DeliveryChallanWorkspace.vue", {
		defineProps: () => props, useRouter: noop,
		useCollapsedStockGuard: () => ({ collapsedStockNotice: Vue.computed(() => "") }),
		autofillSingleOptions: async () => ({}), forgetAutofill: () => {},
	}, "applyWorkspace, form")
	state.applyWorkspace({ record: {}, values: { lot: "", process_name: "Server Process", posting_date: "2026-10-23" }, permissions: { can_create: 1 } })
	assert.equal(state.form.lot, "LOT-1")
	assert.equal(state.form.process_name, "Server Process")
	assert.equal(state.form.posting_date, "2026-10-23")
	assert.ok(!("unknown_field" in state.form))
})

test("a new GRN preselects the filtered source and keeps the other filters for the draft", () => {
	fromList("YRP Goods Received Note", { against: "YRP Work Order", against_id: "WO-1", supplier: "Unit One" })
	const page = setup("FabricGoodsReceivedNote.vue", {
		defineProps: () => ({ sourceContext: {}, name: "" }),
		useRoute: () => ({ params: {}, query: {} }), useRouter: noop,
		hasGoodsReceivedNoteSource: (source) => Boolean(source?.work_order || source?.purchase_order || source?.against_id || source?.duplicate_from),
	}, "filterSource, newDefaults, needsSource")
	assert.equal(page.needsSource.value, true)
	assert.deepEqual(page.filterSource, { against: "YRP Work Order", against_id: "WO-1", delivery_challan: "" })
	assert.deepEqual(page.newDefaults, { supplier: "Unit One" })
})

test("the GRN source picker starts from the filtered source", async () => {
	const picker = setup("fabric-store/GoodsReceivedNoteSourcePicker.vue", {
		defineProps: () => ({ initialSource: { against: "Purchase Order", against_id: "PO-1" } }),
		getList: async () => [],
		goodsReceivedNoteSource: (against, againstId) => against === "Purchase Order" ? { purchase_order: againstId } : { work_order: againstId },
	}, "source")
	await settle()
	assert.deepEqual(picker.source.value, { purchase_order: "PO-1" })
})

test("the GRN draft keeps source values and runs the party follow-ups for filled ones", async () => {
	const addresses = []
	const props = { name: "", sourceContext: { work_order: "WO-1" }, newDefaults: { supplier: "Filter Supplier", lot: "LOT-1", delivery_location: "Unit Two" } }
	const state = setup("fabric-store/GoodsReceivedNoteWorkspace.vue", {
		defineProps: () => props, useRouter: noop,
		useCollapsedStockGuard: () => ({ collapsedStockNotice: Vue.computed(() => "") }),
		prepareActualDiaGroups: (groups) => groups, forgetAutofill: () => {}, watch: () => {},
		autofillGoodsReceivedNoteLocation: async () => ({}),
		getGoodsReceivedNoteDeliveryAddress: async (party) => { addresses.push(party); return "Addr Two" },
		getGoodsReceivedNoteSupplierAddress: async (party) => { addresses.push(party); return "Supplier Addr" },
		GRN_LOCATION_AUTOFILL: { supplier: {}, delivery_location: {} },
	}, "applyWorkspace, form")
	state.applyWorkspace({ record: {}, values: { supplier: "WO Supplier", lot: "", delivery_location: "", delivery_address: "" } })
	await settle()
	assert.equal(state.form.supplier, "WO Supplier")
	assert.equal(state.form.lot, "LOT-1")
	assert.equal(state.form.delivery_location, "Unit Two")
	assert.equal(state.form.delivery_address, "Addr Two")
	assert.deepEqual(addresses, ["Unit Two"])
})

test("a new Work Order applies filtered source and party values through the editor's own changes", async () => {
	fromList("YRP Work Order", { lot: "LOT-1", process_name: "Stitching", supplier: "Unit A", wo_date: "2020-01-01", comments: "From list" })
	const page = setup("FabricWorkOrderEditorPage.vue", { defineProps: () => ({}), useRoute: () => ({ params: {}, query: {} }), useRouter: noop }, "newDefaults")
	const parties = []
	const state = setup("fabric-store/WorkOrderEditor.vue", {
		defineProps: () => ({ name: "", source: {}, newDefaults: page.newDefaults }),
		getWorkOrderEditor: async () => ({ values: { lot: "", process_name: "", item: "", production_detail: "", supplier: "", supplier_address: "", wo_date: "2026-10-23", comments: "" } }),
		getWorkOrderSelectionContext: async () => ({ options: [{ item: "Shirt", production_detail: "IPD-1" }], item_options: ["Shirt"] }),
		changeWorkOrderParty: async (form, fieldname, value) => { parties.push([fieldname, value]); form[fieldname] = value; form.supplier_address = "Addr A" },
		defaultOption, forgetAutofill: () => {},
	}, "load, form, dirty")
	await state.load()
	assert.deepEqual([state.form.lot, state.form.process_name, state.form.item, state.form.production_detail], ["LOT-1", "Stitching", "Shirt", "IPD-1"])
	assert.deepEqual(parties, [["supplier", "Unit A"]])
	assert.equal(state.form.supplier_address, "Addr A")
	assert.equal(state.form.wo_date, "2026-10-23")
	assert.equal(state.form.comments, "From list")
	assert.equal(state.dirty.value, false)
})

test("an edited Work Order ignores staged filters", () => {
	fromList("YRP Work Order", { lot: "LOT-1" })
	const page = setup("FabricWorkOrderEditorPage.vue", { defineProps: () => ({}), useRoute: () => ({ params: { workOrderId: "WO-1" }, query: {} }), useRouter: noop }, "newDefaults")
	assert.deepEqual(page.newDefaults, {})
})

test("a new Purchase Order prefills empty header fields from the list filters", async () => {
	fromList("Purchase Order", { supplier: "Unit A", transaction_date: "2020-01-01", not_a_field: 1 })
	const page = setup("FabricPurchaseOrderEditorPage.vue", { defineProps: () => ({}), useRoute: () => ({ params: {}, query: {} }), useRouter: noop }, "newDefaults")
	const state = setup("fabric-store/PurchaseOrderEditor.vue", {
		defineProps: () => ({ name: "", source: {}, newDefaults: page.newDefaults }),
		getPurchaseOrderEditor: async () => ({ values: { transaction_date: "2026-10-23" }, item_groups: [] }),
		createPurchaseOrderDraftRevision, createPurchaseOrderPreviewController, loadPurchaseOrderGroups,
	}, "load, form")
	await state.load()
	assert.equal(state.form.supplier, "Unit A")
	assert.equal(state.form.transaction_date, "2026-10-23")
	assert.ok(!("not_a_field" in state.form))
})

test("a new stock document from the Stock Transfers list takes its filters into empty header fields", async () => {
	globalThis.window = { history: { state: { current: LIST_PATH } } }
	stageNewDocumentDefaults("YRP Stock Entry", { purpose: "Material Receipt", supplier: "Unit A" }, LIST_PATH)
	const list = setup("fabric-store/FabricStockTransfers.vue", {
		defineProps: () => ({ capability: { operations: { stock_entry: { doctype: "YRP Stock Entry" } } } }),
	}, "createDocument, newDefaults")
	list.createDocument()
	assert.deepEqual(list.newDefaults.value, { purpose: "Material Receipt", supplier: "Unit A" })
	const changed = []
	const settled = async () => {}
	const state = setup("fabric-store/FabricStockOperationDialog.vue", {
		defineProps: () => ({ visible: false, operation: "stock_entry", name: "", sourceContext: {}, newDefaults: list.newDefaults.value }),
		useActionConfirmation: noop,
		getFabricStockOperationEditor: async () => ({ defaults: { purpose: "Material Transfer", posting_date: "2026-10-23" }, permissions: {} }),
		buildStockHeaderFields: () => [],
		createWarehouseCheck: () => ({ supplierChanged: () => {}, settled }),
		createSupplierAutofill: () => ({ supplierChanged: (_operation, fieldname) => changed.push(fieldname), forget: () => {}, settled }),
		createStockEntryAutofill: () => ({ locationChanged: () => {}, forget: () => {}, settled }),
	}, "load, form, dirty")
	await state.load()
	assert.equal(state.form.purpose, "Material Transfer")
	assert.equal(state.form.supplier, "Unit A")
	assert.deepEqual(changed, ["supplier"])
	assert.equal(state.dirty.value, false)
})
