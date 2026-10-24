import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { reactive } from "vue"

import { changePurchaseOrderDeliveryLocation } from "../src/departments/fabric-store/purchaseOrderDelivery.js"

const warehousesBySupplier = { "Unit A": ["WH A"], "Unit B": ["WH B"], "Unit Many": ["WH M1", "WH M2"] }
const calls = []
const fetchOptions = async (args) => {
	calls.push(args)
	const warehouses = warehousesBySupplier[args.supplier] || []
	return { supplier: args.supplier, warehouse: warehouses.length === 1 ? warehouses[0] : null }
}
const newForm = (values = {}) => reactive({ default_delivery_location: "", set_warehouse: "", ...values })

test("a delivery location with one Warehouse fills the delivery warehouse", async () => {
	const form = newForm()
	await changePurchaseOrderDeliveryLocation(form, "Unit A", { fetchOptions })
	assert.equal(form.default_delivery_location, "Unit A")
	assert.equal(form.set_warehouse, "WH A")
	assert.deepEqual(calls.at(-1), { supplier: "Unit A" })
})

test("a delivery location with several Warehouses leaves the warehouse empty", async () => {
	const form = newForm({ default_delivery_location: "Unit A", set_warehouse: "WH A" })
	await changePurchaseOrderDeliveryLocation(form, "Unit Many", { fetchOptions })
	assert.equal(form.set_warehouse, "")
})

test("changing or clearing the location replaces a warehouse of the previous location", async () => {
	const form = newForm()
	await changePurchaseOrderDeliveryLocation(form, "Unit A", { fetchOptions })
	await changePurchaseOrderDeliveryLocation(form, "Unit B", { fetchOptions })
	assert.equal(form.set_warehouse, "WH B")
	await changePurchaseOrderDeliveryLocation(form, "", { fetchOptions })
	assert.equal(form.default_delivery_location, "")
	assert.equal(form.set_warehouse, "")
})

test("a warehouse picked while the lookup is in flight is kept", async () => {
	const form = newForm()
	let release
	const slowFetch = (args) => new Promise((resolve) => { release = () => resolve(fetchOptions(args)) })
	const pending = changePurchaseOrderDeliveryLocation(form, "Unit A", { fetchOptions: slowFetch })
	form.set_warehouse = "WH Manual"
	release()
	await pending
	assert.equal(form.set_warehouse, "WH Manual")
})

test("re-selecting the same location keeps the chosen warehouse without a lookup", async () => {
	const form = newForm({ default_delivery_location: "Unit Many", set_warehouse: "WH M2" })
	const before = calls.length
	await changePurchaseOrderDeliveryLocation(form, "Unit Many", { fetchOptions })
	assert.equal(form.set_warehouse, "WH M2")
	assert.equal(calls.length, before)
})

test("the Purchase Order editor fills the warehouse when the delivery location changes", () => {
	const source = readFileSync(new URL("../src/departments/fabric-store/PurchaseOrderEditor.vue", import.meta.url), "utf8")
	assert.match(source, /changePurchaseOrderDeliveryLocation\(form, value/)
})
