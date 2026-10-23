import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { reactive } from "vue"

import { createStockEntryAutofill } from "../src/departments/fabric-store/stockEntryAutofill.js"
import { buildStockHeaderFields, createWarehouseCheck } from "../src/departments/fabric-store/stockHeaderFields.js"

const editor = { posting_fields: [] }
const warehousesBySupplier = { "Unit A": ["WH A"], "Unit B": ["WH B"], "Unit Many": ["WH M1", "WH M2"] }
const fetchOptions = async ({ supplier }) => ({ supplier, warehouse: warehousesBySupplier[supplier]?.length === 1 ? warehousesBySupplier[supplier][0] : null })
const belongs = async (warehouse, supplier) => (warehousesBySupplier[supplier] || []).includes(warehouse)

function setup(purpose, values = {}) {
	const form = reactive({ purpose, from_supplier: "", from_warehouse: "", to_supplier: "", to_warehouse: "", ...values })
	const errors = []
	const check = createWarehouseCheck(form, belongs, (reason) => errors.push(reason))
	const autofill = createStockEntryAutofill(form, check, () => buildStockHeaderFields("stock_entry", form, editor), { fetchOptions, onError: (reason) => errors.push(reason) })
	const choose = async (fieldname, value, operation = "stock_entry") => {
		form[fieldname] = value
		check.supplierChanged(fieldname)
		autofill.locationChanged(operation, fieldname)
		await autofill.settled()
	}
	return { form, choose, errors, autofill }
}

test("a location with one Warehouse fills its empty paired Warehouse", async () => {
	const { form, choose, errors } = setup("Send to Warehouse")
	await choose("from_supplier", "Unit A")
	await choose("to_supplier", "Unit B")
	assert.equal(form.from_warehouse, "WH A")
	assert.equal(form.to_warehouse, "WH B")
	assert.deepEqual(errors, [])
})

test("a location with several Warehouses leaves the Warehouse empty", async () => {
	const { form, choose } = setup("Send to Warehouse")
	await choose("to_supplier", "Unit Many")
	assert.equal(form.to_warehouse, "")
})

test("a Warehouse the user picked for the location is kept", async () => {
	const { form, choose } = setup("Send to Warehouse", { to_supplier: "Unit Many", to_warehouse: "WH M2" })
	await choose("to_supplier", "Unit Many")
	assert.equal(form.to_warehouse, "WH M2")
})

test("a stale auto-filled Warehouse is replaced or cleared when the location changes", async () => {
	const { form, choose } = setup("Material Issue")
	await choose("from_supplier", "Unit A")
	await choose("from_supplier", "Unit B")
	assert.equal(form.from_warehouse, "WH B")
	await choose("from_supplier", "Unit Many")
	assert.equal(form.from_warehouse, "")
	await choose("from_supplier", "Unit A")
	await choose("from_supplier", "")
	assert.equal(form.from_warehouse, "")
})

test("a user Warehouse from the old location is cleared by the mismatch check, then the new single Warehouse fills", async () => {
	const { form, choose } = setup("Send to Warehouse", { to_supplier: "Unit Many", to_warehouse: "WH M1" })
	await choose("to_supplier", "Unit A")
	assert.equal(form.to_warehouse, "WH A")
})

test("read-only or hidden Warehouses are not filled", async () => {
	const receipt = setup("Material Receipt")
	await receipt.choose("from_supplier", "Unit A")
	assert.equal(receipt.form.from_warehouse, "")
	await receipt.choose("to_supplier", "Unit B")
	assert.equal(receipt.form.to_warehouse, "WH B")
	const issue = setup("Material Issue")
	await issue.choose("to_supplier", "Unit B")
	assert.equal(issue.form.to_warehouse, "")
})

test("other stock operations and fields are ignored", async () => {
	const { form, choose } = setup("Send to Warehouse")
	await choose("from_supplier", "Unit A", "stock_update")
	assert.equal(form.from_warehouse, "")
})

test("forget drops the auto-filled marker so a loaded value counts as the user's", async () => {
	const { form, choose, autofill } = setup("Material Issue")
	await choose("from_supplier", "Unit A")
	autofill.forget()
	form.from_supplier = "Unit B"
	autofill.locationChanged("stock_entry", "from_supplier")
	await autofill.settled()
	assert.equal(form.from_warehouse, "WH A")
})

test("the Stock Entry dialog queues the autofill on location change and awaits it before Save", () => {
	const source = readFileSync(new URL("../src/departments/fabric-store/FabricStockOperationDialog.vue", import.meta.url), "utf8")
	assert.match(source, /stockEntryAutofill\.locationChanged\(props\.operation, fieldname\)/)
	assert.match(source, /await stockEntryAutofill\.settled\(\)/)
	assert.match(source, /stockEntryAutofill\.forget\(\)/)
})
