import assert from "node:assert/strict"
import test from "node:test"
import { dispatchEntrySource, dispatchInitialState, dispatchRowSizes } from "../src/departments/finishing/finishingEntries.js"

const row = {
	sizes: ["S", "M", "L", "XL", "2XL"],
	values: { "2XL": { qty: 1 }, L: { qty: 2 }, M: { qty: 3 }, S: { qty: 4 }, XL: { qty: 5 } },
	total: { total_qty: 15 },
}

test("dispatch size columns follow the server's Item mapping order", () => {
	assert.deepEqual(dispatchRowSizes(row), ["S", "M", "L", "XL", "2XL"])
	assert.deepEqual(dispatchEntrySource(row).sizes, ["S", "M", "L", "XL", "2XL"])
	assert.deepEqual(Object.keys(dispatchInitialState(row).legacy), ["S", "M", "L", "XL", "2XL"])
})

test("numeric sizes keep mapping order instead of object key order", () => {
	const numeric = { sizes: ["100", "75", "80"], values: { 100: { qty: 1 }, 75: { qty: 1 }, 80: { qty: 1 } } }
	assert.deepEqual(dispatchRowSizes(numeric), ["100", "75", "80"])
})

test("rows without sizes fall back to their value keys", () => {
	assert.deepEqual(dispatchRowSizes({ values: { S: {}, M: {} } }), ["S", "M"])
})
