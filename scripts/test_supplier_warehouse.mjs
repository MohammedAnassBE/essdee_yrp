#!/usr/bin/env node

import assert from "node:assert/strict"

import { setDispatchSupplier } from "../frontend/src/departments/finishing/supplierWarehouse.js"

const requests = []
globalThis.window = { csrf_token: "" }
globalThis.fetch = (_url, options) => new Promise((resolve, reject) => {
	requests.push({ supplier: JSON.parse(options.body).supplier, resolve, reject })
})

const response = (message) => ({
	ok: true,
	status: 200,
	json: async () => ({ message }),
})
const form = {}
const oldSupplier = setDispatchSupplier(form, "from", "SUP-A")
const newSupplier = setDispatchSupplier(form, "from", "SUP-B")

assert.deepEqual(requests.map(({ supplier }) => supplier), ["SUP-A", "SUP-B"])
requests[1].resolve(response(["WH-B"]))
assert.equal(await newSupplier, "")
requests[0].reject(new Error("Unable to load SUP-A"))
assert.equal(await oldSupplier, "", "an out-of-order failure from a stale Supplier is ignored")
assert.deepEqual(form, { from_supplier: "SUP-B", from_warehouse: "WH-B" })

console.log("supplierWarehouse.js: OK")
