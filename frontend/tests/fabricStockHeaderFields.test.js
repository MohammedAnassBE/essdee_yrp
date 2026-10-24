import assert from "node:assert/strict"
import test from "node:test"

import { buildStockHeaderFields, clearMismatchedWarehouse, createSupplierAutofill, createWarehouseCheck } from "../src/departments/fabric-store/stockHeaderFields.js"

const editor = { purpose_options: ["Stock Reconciliation", "Opening Stock"], update_type_options: ["Add", "Remove"], posting_fields: [] }
const names = (fields) => fields.map((field) => field.fieldname)
const field = (fields, fieldname) => fields.find((candidate) => candidate.fieldname === fieldname)

test("stock reconciliation shows supplier before warehouse and filters warehouse by supplier", () => {
	const fields = buildStockHeaderFields("stock_reconciliation", { default_supplier: "Essdee Fabric Store - Tiruppur" }, editor)
	assert.deepEqual(names(fields), ["purpose", "default_supplier", "default_warehouse", "comments"])
	assert.deepEqual(field(fields, "default_warehouse").link_filters, { disabled: 0, supplier: "Essdee Fabric Store - Tiruppur" })
})

test("stock update shows supplier before warehouse and filters warehouse by supplier", () => {
	const fields = buildStockHeaderFields("stock_update", { supplier: "SUP-1" }, editor)
	assert.deepEqual(names(fields), ["update_type", "supplier", "warehouse", "comments"])
	assert.deepEqual(field(fields, "warehouse").link_filters, { disabled: 0, supplier: "SUP-1" })
})

test("warehouse is unfiltered by supplier when no supplier is selected, like Desk", () => {
	assert.deepEqual(field(buildStockHeaderFields("stock_reconciliation", {}, editor), "default_warehouse").link_filters, { disabled: 0 })
	assert.deepEqual(field(buildStockHeaderFields("stock_update", {}, editor), "warehouse").link_filters, { disabled: 0 })
})

test("stock entry keeps each location before its warehouse with the paired filter", () => {
	const fields = buildStockHeaderFields("stock_entry", { purpose: "Send to Warehouse", from_supplier: "A", to_supplier: "B" }, editor)
	assert.deepEqual(names(fields), ["purpose", "from_supplier", "to_supplier", "from_warehouse", "to_warehouse", "skip_transit", "transfer_supplier", "vehicle_no", "terms_and_condition", "additional_amount", "comments"])
	assert.equal(field(fields, "from_warehouse").link_filters.supplier, "A")
	assert.equal(field(fields, "to_warehouse").link_filters.supplier, "B")
})

test("stock entry shows the Desk transport and remarks fields, Additional Amount only for Send to Warehouse", () => {
	const issue = buildStockHeaderFields("stock_entry", { purpose: "Material Issue" }, editor)
	assert.deepEqual(names(issue).slice(-4), ["transfer_supplier", "vehicle_no", "terms_and_condition", "comments"])
	assert.equal(field(issue, "vehicle_no").fieldtype, "Data")
	assert.equal(field(issue, "comments").fieldtype, "Small Text")
	assert.equal(field(issue, "terms_and_condition").options, "YRP Terms and Condition")
	assert.deepEqual(field(issue, "transfer_supplier").link_filters, { disabled: 0 })
	assert.equal(field(buildStockHeaderFields("stock_entry", { purpose: "Send to Warehouse" }, editor), "additional_amount").fieldtype, "Currency")
})

test("protected completion entries show the added fields read-only", () => {
	const fields = buildStockHeaderFields("stock_entry", { purpose: "DC Completion" }, { ...editor, protected_completion: true })
	for (const fieldname of ["transfer_supplier", "vehicle_no", "terms_and_condition", "comments"]) assert.equal(field(fields, fieldname).read_only, true, fieldname)
})

test("changing supplier clears only a warehouse that does not belong to it", async () => {
	const owned = { "W-A": "A" }
	const belongs = async (warehouse, supplier) => owned[warehouse] === supplier
	const mismatched = { default_supplier: "B", default_warehouse: "W-A" }
	await clearMismatchedWarehouse(mismatched, "default_supplier", belongs)
	assert.equal(mismatched.default_warehouse, "")
	const matching = { supplier: "A", warehouse: "W-A" }
	await clearMismatchedWarehouse(matching, "supplier", belongs)
	assert.equal(matching.warehouse, "W-A")
	const cleared = { from_supplier: "", from_warehouse: "W-A" }
	await clearMismatchedWarehouse(cleared, "from_supplier", belongs)
	assert.equal(cleared.from_warehouse, "W-A")
})

test("a stale supplier check does not clear a warehouse picked meanwhile", async () => {
	const form = { to_supplier: "B", to_warehouse: "W-A" }
	await clearMismatchedWarehouse(form, "to_supplier", async () => { form.to_warehouse = "W-B"; return false })
	assert.equal(form.to_warehouse, "W-B")
})

test("save can wait for a pending supplier check before reading the warehouse", async () => {
	const form = { default_supplier: "B", default_warehouse: "W-A" }
	let resolve
	const check = createWarehouseCheck(form, () => new Promise((done) => { resolve = done }), assert.fail)
	check.supplierChanged("default_supplier")
	const settled = check.settled()
	await Promise.resolve()
	assert.equal(form.default_warehouse, "W-A")
	resolve(false)
	await settled
	assert.equal(form.default_warehouse, "")
})

test("a failed supplier check clears the warehouse and reports the error", async () => {
	const form = { supplier: "B", warehouse: "W-A" }
	const errors = []
	const check = createWarehouseCheck(form, async () => { throw new Error("lookup failed") }, (reason) => errors.push(reason.message))
	check.supplierChanged("supplier")
	await check.settled()
	assert.equal(form.warehouse, "")
	assert.deepEqual(errors, ["lookup failed"])
})

const singleOptions = { "One WH": { warehouse: "W-ONE" }, "Two WH": { warehouse: null }, "Other One": { warehouse: "W-OTHER" } }
const autofillFor = (form, check = { settled: async () => {} }) => createSupplierAutofill(form, check, { fetchOptions: async ({ supplier }) => singleOptions[supplier], onError: assert.fail })

test("stock reconciliation fills the only warehouse of the chosen supplier", async () => {
	const form = { default_supplier: "One WH", default_warehouse: "" }
	const autofill = autofillFor(form)
	autofill.supplierChanged("stock_reconciliation", "default_supplier")
	await autofill.settled()
	assert.equal(form.default_warehouse, "W-ONE")
})

test("stock reconciliation leaves the warehouse empty when the supplier has several", async () => {
	const form = { default_supplier: "Two WH", default_warehouse: "" }
	const autofill = autofillFor(form)
	autofill.supplierChanged("stock_reconciliation", "default_supplier")
	await autofill.settled()
	assert.equal(form.default_warehouse, "")
})

test("stock reconciliation replaces or clears a stale auto-filled warehouse but keeps a picked one", async () => {
	const form = { default_supplier: "One WH", default_warehouse: "" }
	const autofill = autofillFor(form)
	autofill.supplierChanged("stock_reconciliation", "default_supplier")
	form.default_supplier = "Other One"
	autofill.supplierChanged("stock_reconciliation", "default_supplier")
	await autofill.settled()
	assert.equal(form.default_warehouse, "W-OTHER")
	form.default_supplier = "Two WH"
	autofill.supplierChanged("stock_reconciliation", "default_supplier")
	await autofill.settled()
	assert.equal(form.default_warehouse, "")
	form.default_warehouse = "W-PICKED"
	form.default_supplier = "One WH"
	autofill.supplierChanged("stock_reconciliation", "default_supplier")
	await autofill.settled()
	assert.equal(form.default_warehouse, "W-PICKED")
})

test("supplier autofill runs after the mismatch check clears a foreign warehouse", async () => {
	const form = { default_supplier: "One WH", default_warehouse: "W-FOREIGN" }
	const check = createWarehouseCheck(form, async () => false, assert.fail)
	const autofill = autofillFor(form, check)
	check.supplierChanged("default_supplier")
	autofill.supplierChanged("stock_reconciliation", "default_supplier")
	await autofill.settled()
	assert.equal(form.default_warehouse, "W-ONE")
})

test("supplier autofill ignores operations and fields without a mapping", async () => {
	const form = { supplier: "One WH", warehouse: "", default_supplier: "One WH", default_warehouse: "" }
	const autofill = autofillFor(form)
	autofill.supplierChanged("stock_reconciliation", "purpose")
	autofill.supplierChanged("lot_transfer", "default_supplier")
	await autofill.settled()
	assert.equal(form.default_warehouse, "")
})

test("stock update fills the only warehouse of the chosen supplier and reports the change", async () => {
	const form = { supplier: "One WH", warehouse: "" }
	const changes = []
	const autofill = createSupplierAutofill(form, { settled: async () => {} }, { fetchOptions: async ({ supplier }) => singleOptions[supplier], onChange: (change) => changes.push(change), onError: assert.fail })
	autofill.supplierChanged("stock_update", "supplier")
	await autofill.settled()
	assert.equal(form.warehouse, "W-ONE")
	assert.deepEqual(changes, [{ warehouse: "W-ONE" }])
})

test("stock update replaces or clears a stale auto-filled warehouse but keeps a picked one", async () => {
	const form = { supplier: "One WH", warehouse: "" }
	const autofill = autofillFor(form)
	autofill.supplierChanged("stock_update", "supplier")
	await autofill.settled()
	form.supplier = "Other One"
	autofill.supplierChanged("stock_update", "supplier")
	await autofill.settled()
	assert.equal(form.warehouse, "W-OTHER")
	form.supplier = "Two WH"
	autofill.supplierChanged("stock_update", "supplier")
	await autofill.settled()
	assert.equal(form.warehouse, "")
	form.warehouse = "W-PICKED"
	form.supplier = "One WH"
	autofill.supplierChanged("stock_update", "supplier")
	await autofill.settled()
	assert.equal(form.warehouse, "W-PICKED")
})

test("forget drops the auto-fill record so a loaded warehouse counts as the user's", async () => {
	const form = { default_supplier: "One WH", default_warehouse: "" }
	const autofill = autofillFor(form)
	autofill.supplierChanged("stock_reconciliation", "default_supplier")
	await autofill.settled()
	autofill.forget()
	form.default_supplier = "Two WH"
	autofill.supplierChanged("stock_reconciliation", "default_supplier")
	await autofill.settled()
	assert.equal(form.default_warehouse, "W-ONE")
})
