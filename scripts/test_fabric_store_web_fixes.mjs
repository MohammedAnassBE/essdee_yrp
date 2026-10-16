import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import vm from "node:vm"
import { computed, nextTick, reactive, ref, watch } from "../frontend/node_modules/vue/index.mjs"
import { callMethod } from "../frontend/src/api/frappe.js"
import { mapFieldError, requiredFieldErrors } from "../frontend/src/utils/fieldErrors.js"
import { mergeStockItemDraft } from "../frontend/src/utils/stockItemComposer.js"
import * as purchaseOrderHelpers from "../frontend/src/utils/purchaseOrder.js"

function setup(filename, bindings, exposed) {
	const source = readFileSync(filename, "utf8").match(/<script setup>([\s\S]*?)<\/script>/)[1]
		.replace(/^import[\s\S]*?from ["'][^"']+["'];?\s*$/gm, "")
	const globals = { computed, nextTick, reactive, ref, watch, onMounted() {}, onBeforeUnmount() {}, onBeforeRouteLeave() {}, defineExpose() {}, ...bindings }
	return new Function(...Object.keys(globals), `${source}\nreturn { ${exposed} }`)(...Object.values(globals))
}
const fields = [{ fieldname: "posting_date", label: "Posting Date", reqd: true }, { fieldname: "posting_time", label: "Posting Time", reqd: true }]
assert.deepEqual(requiredFieldErrors(fields, { posting_time: "10:00:00" }), { posting_date: "Posting Date is required." })
for (const message of ["Value missing for YRP Stock Reconciliation: Posting Date", "MandatoryError: Value missing for YRP Stock Reconciliation: <b>Posting Date</b>", "Posting Date is required."]) {
	assert.deepEqual(mapFieldError(new Error(message), fields), { fields: { posting_date: "Posting Date is required." }, message: "" })
}
assert.deepEqual(mapFieldError(new Error("Posting Time must be earlier than now."), fields).fields, { posting_time: "Posting Time must be earlier than now." })
assert.equal(mapFieldError(new Error("Error: Insufficient stock."), fields).message, "Insufficient stock.")

assert.deepEqual(mapFieldError(new Error("Value missing for YRP Stock Reconciliation: Posting Date\nError: Insufficient stock."), fields), { fields: { posting_date: "Posting Date is required." }, message: "Insufficient stock." })
assert.equal(mapFieldError(new Error("[YRP Stock Reconciliation, SRC-1]: Insufficient stock."), fields).message, "Insufficient stock.")
assert.equal(mapFieldError(new Error(""), fields).message, "Unable to save this document.")
const originalWindow = globalThis.window
const originalFetch = globalThis.fetch
globalThis.window = {}
globalThis.fetch = async () => ({ ok: false, status: 417, json: async () => ({ exc_type: "MandatoryError", exc: "traceback", _server_messages: JSON.stringify([JSON.stringify({ message: "Value missing for YRP Stock Reconciliation: Posting Date" })]) }) })
try {
	await assert.rejects(callMethod("mock.save"), reason => {
		assert.equal(reason.exc_type, "MandatoryError")
		assert.ok(reason.serverMessages)
		assert.equal(mapFieldError(reason, fields).fields.posting_date, "Posting Date is required.")
		return true
	})
} finally { globalThis.window = originalWindow; globalThis.fetch = originalFetch }

const operationProps = reactive({ visible: false, operation: "stock_reconciliation", name: "", expectedModified: "", sourceContext: {}, initialEditor: null })
let serverError, saves = []
const defaults = { purpose: "Stock Reconciliation", posting_date: "2026-10-15", posting_time: "12:34:56", default_warehouse: "Stores", edit_posting_date_and_time: 0 }
const operation = setup("frontend/src/departments/fabric-store/FabricStockOperationDialog.vue", {
	defineProps: () => operationProps, defineEmits: () => () => {}, useActionConfirmation: () => () => {}, mapFieldError, requiredFieldErrors,
	getFabricStockOperationEditor: async () => ({ defaults, posting_fields: fields, permissions: { can_create: true, can_submit: true }, item_groups: [{ items: [{ name: "Yarn" }] }], purpose_options: ["Stock Reconciliation"] }),
	saveFabricStockOperation: async (...args) => { saves.push(args); if (serverError) throw serverError; return { record: { name: "STOCK-1" } } },
}, "load, save, form, headerFields, fieldErrors, error, editor, updateField, itemDetails")
await operation.load()
assert.equal(operation.form.posting_date, "2026-10-15")
assert.equal(operation.form.posting_time, "12:34:56")
assert.ok(operation.headerFields.value.filter(field => field.fieldname.startsWith("posting_")).every(field => field.reqd && field.read_only))
assert.ok(operation.headerFields.value.find(field => field.fieldname === "purpose").reqd)
assert.ok(operation.headerFields.value.find(field => field.fieldname === "default_warehouse").reqd)
operation.updateField("edit_posting_date_and_time", 1)
assert.ok(operation.headerFields.value.filter(field => field.fieldname.startsWith("posting_")).every(field => field.reqd && !field.read_only))
operation.updateField("posting_date", "")
const stagedItems = operation.itemDetails.value
operation.itemDetails.value = []
await operation.save(false)
assert.equal(saves.length, 0)
assert.equal(operation.fieldErrors.value.posting_date, "Posting Date is required.")
operation.itemDetails.value = stagedItems
operation.updateField("posting_date", "2026-10-15")
assert.equal(operation.fieldErrors.value.posting_date, undefined)
serverError = new Error("Value missing for YRP Stock Reconciliation: Posting Date")
await operation.save(false)
assert.equal(operation.fieldErrors.value.posting_date, "Posting Date is required.")
assert.equal(operation.error.value, "")
serverError = new Error("Error: Insufficient stock.")
await operation.save(false)
assert.equal(operation.error.value, "Insufficient stock.")
serverError = null
await operation.save(false)
assert.equal(saves.at(-1)[1].posting_date, "2026-10-15")
operationProps.operation = "stock_entry"
operation.updateField("purpose", "Material Receipt")
let headers = operation.headerFields.value
assert.equal(headers.find(field => field.fieldname === "from_warehouse").reqd, false)
assert.equal(headers.find(field => field.fieldname === "from_warehouse").read_only, true)
assert.equal(headers.find(field => field.fieldname === "to_warehouse").reqd, true)
operation.updateField("purpose", "Send to Warehouse")
assert.ok(operation.headerFields.value.some(field => field.fieldname === "skip_transit"))
operationProps.initialEditor = { defaults: { ...defaults, purpose: "Receive at Warehouse", outgoing_stock_entry: "SEND-1", from_warehouse: "From", to_warehouse: "To" }, posting_fields: fields, purpose_options: ["Receive at Warehouse"], purpose_locked: true, permissions: { can_create: true, can_submit: true }, item_groups: [{ items: [{ name: "Yarn", values: { default: { qty: 5 } } }] }] }
await operation.load()
headers = operation.headerFields.value
assert.ok(headers.find(field => field.fieldname === "purpose").read_only)
assert.ok(headers.find(field => field.fieldname === "outgoing_stock_entry").read_only)
assert.ok(headers.find(field => field.fieldname === "to_warehouse").read_only)
await operation.save(true)
assert.equal(saves.at(-1)[1].outgoing_stock_entry, "SEND-1")
assert.equal(saves.at(-1)[2].submit, true)

assert.deepEqual(operation.headerFields.value.find(field => field.fieldname === "purpose").options.split("\n"), operation.editor.value.purpose_options || [])
const composerEvents = []
const composer = setup("frontend/src/components/stock/StockItemComposer.vue", {
	defineProps: () => ({ operation: "stock_entry", purpose: "Material Receipt", editor: { dimensions: [] }, modelValue: [], entryDefaults: {}, entryFields: [] }),
	defineEmits: () => (...args) => composerEvents.push(args), mergeStockItemDraft,
}, "itemSchema, quantities, receiptRates, stageItem, groups, prepareQuantities")
composer.itemSchema.value = { item: "Yarn", default_uom: "Kg", attributes: [] }
composer.prepareQuantities()
composer.quantities.default = 5
composer.receiptRates.default = 45
await composer.stageItem()
assert.equal(composer.groups.value[0].items[0].values.default.rate, 45)
assert.equal(composerEvents.find(([name]) => name === "update:modelValue")[1][0].items[0].values.default.qty, 5)

const transactionEvents = []
let documentLoads = 0
const transaction = setup("frontend/src/components/documents/DocumentTransactionDialog.vue", {
	defineProps: () => ({ visible: false, doctype: "YRP Stock Entry", name: "SEND-1" }),
	defineEmits: () => (...args) => transactionEvents.push(args), useActionConfirmation: () => () => {},
	getFabricStoreDocument: async () => { documentLoads += 1; return { record: { doctype: "YRP Stock Entry", name: "SEND-1" }, transit: { status: documentLoads > 1 ? "Received" : "In transit · 0% received" }, actions: { can_end_transit: documentLoads === 1 } } },
	endStockEntryTransit: async name => { assert.equal(name, "SEND-1"); return operationProps.initialEditor },
}, "load, endTransit, receiptEditor, receiptVisible, receiptChanged, payload, stockEntryPath")
await transaction.load()
assert.equal(transaction.payload.value.actions.can_end_transit, true)
await transaction.endTransit()
assert.equal(transaction.receiptVisible.value, true)
assert.equal(transaction.receiptEditor.value.defaults.outgoing_stock_entry, "SEND-1")
await transaction.receiptChanged({ record: { name: "RECEIVE-1" } })
assert.equal(transaction.payload.value.transit.status, "Received")
assert.equal(transaction.payload.value.actions.can_end_transit, false)
assert.equal(transaction.stockEntryPath("RECEIVE-1"), "/app/yrp-stock-entry/RECEIVE-1")
assert.equal(transactionEvents.at(-1)[0], "changed")

let stored = { values: { process_name: null, lot: null, item: null }, permissions: { can_create: true } }
const contexts = []
let holdSelection = false
const selectionWaiters = []
const workOrder = setup("frontend/src/departments/fabric-store/WorkOrderEditor.vue", {
	defineProps: () => ({ name: "", source: {} }), defineEmits: () => () => {}, useToast: () => ({ add() {} }),
	getWorkOrderEditor: async () => structuredClone(stored),
	getWorkOrderSelectionContext: async (...args) => { contexts.push(args); if (holdSelection) return new Promise(resolve => selectionWaiters.push(resolve)); return { options: [{ item: "Fabric", production_detail: "IPD" }], item_options: ["Fabric"] } },
	saveWorkOrder: async values => { stored = { ...stored, values }; return { record: { name: "WO-1" } } },
}, "load, form, changeSource, changeItem, selectionContext, sourceRevision, deliverableDetails, receivableDetails, pendingSourceChange, sourceConfirmVisible, sourceConfirmationVisibilityChanged, confirmSourceChange, save, sourceConfirmTitle")
await workOrder.load()
await workOrder.changeSource("process_name", "")
assert.equal(workOrder.sourceRevision.value, 0, "null and empty are equal; no busy/re-key cycle")
await workOrder.changeSource("process_name", "Knitting")
assert.equal(workOrder.form.process_name, "Knitting")
await workOrder.changeSource("lot", "F0926-49")
assert.deepEqual(contexts, [["F0926-49", "Knitting"]])
assert.deepEqual(workOrder.selectionContext.value.item_options, ["Fabric"])
workOrder.changeItem("Fabric")
await workOrder.save(false)
await workOrder.load()
assert.equal(workOrder.form.process_name, "Knitting")
assert.equal(workOrder.form.lot, "F0926-49")
workOrder.deliverableDetails.value = [{ items: [{ name: "Fabric" }] }]
workOrder.receivableDetails.value = [{ items: [{ name: "Fabric" }] }]
await workOrder.changeSource("process_name", "Dyeing")
assert.equal(workOrder.sourceConfirmTitle.value, "Change Process?")
assert.equal(workOrder.form.process_name, "Knitting")
workOrder.sourceConfirmationVisibilityChanged(false)
assert.equal(workOrder.form.process_name, "Knitting")
await workOrder.changeSource("process_name", "Dyeing")
await workOrder.confirmSourceChange()
assert.equal(workOrder.form.process_name, "Dyeing")
assert.deepEqual(workOrder.deliverableDetails.value, [])
assert.deepEqual(workOrder.receivableDetails.value, [])
holdSelection = true
const changingProcess = workOrder.changeSource("process_name", "Knitting")
await workOrder.changeSource("lot", "F0926-50")
selectionWaiters.shift()({ options: [], item_options: [] })
for (let index = 0; index < 4; index++) await nextTick()
assert.equal(selectionWaiters.length, 1, "a pick during source refresh must be queued, never discarded")
selectionWaiters.shift()({ options: [{ item: "Fabric", production_detail: "IPD" }], item_options: ["Fabric"] })
await changingProcess
assert.equal(workOrder.form.process_name, "Knitting")
assert.equal(workOrder.form.lot, "F0926-50")
const purchaseOrder = setup("frontend/src/departments/fabric-store/PurchaseOrderEditor.vue", {
	...purchaseOrderHelpers, defineProps: () => ({ name: "", source: {} }), defineEmits: () => () => {}, useToast: () => ({}),
}, "form, changeSupplier, loading, sourceRevision")
purchaseOrder.loading.value = false
purchaseOrder.form.supplier = null
await purchaseOrder.changeSupplier("")
assert.equal(purchaseOrder.form.supplier, null)
await purchaseOrder.changeSupplier("S-0005")
assert.equal(purchaseOrder.form.supplier, "S-0005")

const location = { party: "S-0005", supplier_name: "Essdee Fabric Store - Tiruppur", has_address: false, message: "No address is linked to Essdee Fabric Store - Tiruppur (S-0005). Create an address for this location first." }
const dc = setup("frontend/src/departments/fabric-store/DeliveryChallanWorkspace.vue", {
	defineProps: () => ({ name: "", sourceContext: {} }), defineEmits: () => () => {}, useToast: () => ({}), useRouter: () => ({}), watch() {},
	getLocationAddressStatus: async party => ({ ...location, party }),
}, "form, addressStatus, refreshAddressStatus, addressCreationUrl, setField, sourceFieldRevision, fieldKey, dirty, sourceConfirmVisible, sourceConfirmationVisibilityChanged")
dc.form.work_order = null
await dc.setField("work_order", "")
assert.equal(dc.form.work_order, null)
dc.form.work_order = "WO-1"
dc.dirty.value = true
const workOrderField = { fieldname: "work_order", idx: 2 }
const originalFieldKey = dc.fieldKey(workOrderField)
await dc.setField("work_order", "WO-2")
assert.equal(dc.sourceConfirmVisible.value, true)
dc.sourceConfirmationVisibilityChanged(false)
assert.equal(dc.form.work_order, "WO-1")
assert.equal(dc.sourceFieldRevision.value, 1)
assert.equal(dc.fieldKey(workOrderField), originalFieldKey)
dc.form.from_location = "S-0005"; dc.form.supplier = "S-0070"
await dc.refreshAddressStatus()
assert.equal(dc.addressStatus.from_address.message, location.message)
assert.equal(dc.addressStatus.supplier_address.party, "S-0070")
const addressUrl = new URL(dc.addressCreationUrl(location), "https://example.test")
assert.equal(addressUrl.pathname, "/desk/address/new")
assert.equal(addressUrl.searchParams.get("essdee_supplier"), "S-0005")
function loadAddressScript(href) {
	const handlers = {}
	const browser = { location: { href } }
	vm.runInNewContext(readFileSync("essdee_yrp/public/js/address_creation.js", "utf8"), { URL, window: browser, frappe: { ui: { form: { on: (doctype, events) => { handlers[doctype] = events } } } } })
	return { handlers, browser }
}
function addressForm(doc = { links: [] }, isNew = true) {
	return { doc, is_new: () => isNew, add_child: (field, value) => doc[field].push(value), refresh_field() {}, set_value: (field, value) => { doc[field] = value } }
}
for (const prefix of ["app", "desk"]) {
	for (const name of ["new", "new-address-abc"]) {
		for (const firstEvent of ["onload", "refresh"]) {
			const { handlers, browser } = loadAddressScript(`https://example.test/${prefix}/address/${name}?${addressUrl.searchParams}`)
			browser.location.href = "https://example.test/desk/address/new-address-xyz"
			handlers.Address[firstEvent](addressForm({ links: [] }, false))
			const form = addressForm()
			handlers.Address[firstEvent](form)
			assert.deepEqual(JSON.parse(JSON.stringify(form.doc.links)), [{ link_doctype: "Supplier", link_name: "S-0005" }])
			assert.equal(form.doc.address_title, location.supplier_name)
			handlers.Address.onload(form)
			handlers.Address.refresh(form)
			assert.equal(form.doc.links.length, 1)
			const another = addressForm()
			handlers.Address.onload(another)
			handlers.Address.refresh(another)
			assert.deepEqual(another.doc, { links: [] }, "prefill is consumed by only one new Address")
		}
	}
}
const existingLink = addressForm({ address_title: "Chosen title", links: [{ link_doctype: "Supplier", link_name: "S-0005" }] })
loadAddressScript(addressUrl.href).handlers.Address.onload(existingLink)
assert.equal(existingLink.doc.links.length, 1)
assert.equal(existingLink.doc.address_title, "Chosen title")
for (const query of ["", "?address_title=Ordinary", "?essdee_supplier="]) {
	const { handlers, browser } = loadAddressScript(`https://example.test/desk/address/new${query}`)
	browser.location.href = addressUrl.href
	assert.deepEqual(handlers, {}, "ordinary Address creation must not acquire prefill from later navigation")
}
console.log("Fabric Store: posting validation, mapped receipt editor, Work Order confirmation, DC messages and Address redirect tests passed")
