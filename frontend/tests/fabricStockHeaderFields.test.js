import assert from "node:assert/strict"
import test from "node:test"

import { buildStockHeaderFields, clearMismatchedWarehouse, createWarehouseCheck } from "../src/departments/fabric-store/stockHeaderFields.js"

const editor = { purpose_options: ["Stock Reconciliation", "Opening Stock"], update_type_options: ["Add", "Remove"], posting_fields: [] }
const names = (fields) => fields.map((field) => field.fieldname)
const field = (fields, fieldname) => fields.find((candidate) => candidate.fieldname === fieldname)

test("stock reconciliation shows supplier before warehouse and filters warehouse by supplier", () => {
	const fields = buildStockHeaderFields("stock_reconciliation", { default_supplier: "Essdee Fabric Store - Tiruppur" }, editor)
	assert.deepEqual(names(fields), ["purpose", "default_supplier", "default_warehouse"])
	assert.deepEqual(field(fields, "default_warehouse").link_filters, { disabled: 0, supplier: "Essdee Fabric Store - Tiruppur" })
})

test("stock update shows supplier before warehouse and filters warehouse by supplier", () => {
	const fields = buildStockHeaderFields("stock_update", { supplier: "SUP-1" }, editor)
	assert.deepEqual(names(fields), ["update_type", "supplier", "warehouse"])
	assert.deepEqual(field(fields, "warehouse").link_filters, { disabled: 0, supplier: "SUP-1" })
})

test("warehouse is unfiltered by supplier when no supplier is selected, like Desk", () => {
	assert.deepEqual(field(buildStockHeaderFields("stock_reconciliation", {}, editor), "default_warehouse").link_filters, { disabled: 0 })
	assert.deepEqual(field(buildStockHeaderFields("stock_update", {}, editor), "warehouse").link_filters, { disabled: 0 })
})

test("stock entry keeps each location before its warehouse with the paired filter", () => {
	const fields = buildStockHeaderFields("stock_entry", { purpose: "Send to Warehouse", from_supplier: "A", to_supplier: "B" }, editor)
	assert.deepEqual(names(fields), ["purpose", "from_supplier", "to_supplier", "from_warehouse", "to_warehouse", "skip_transit"])
	assert.equal(field(fields, "from_warehouse").link_filters.supplier, "A")
	assert.equal(field(fields, "to_warehouse").link_filters.supplier, "B")
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
