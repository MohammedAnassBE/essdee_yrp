import assert from "node:assert/strict"
import test from "node:test"
import { getMeta } from "../src/api/frappe.js"

const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r }); return { promise, resolve } }

test("metadata shares pending identity requests, returns copies and refetches settled data", async () => {
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { location: { host: "site" }, frappe: { session: { user: "one" } } }
	const pending = []
	globalThis.fetch = () => { const item = deferred(); pending.push(item); return item.promise }
	const response = () => ({ ok: true, status: 200, json: async () => ({ docs: [{ name: "Item", fields: [{ label: "Original" }] }] }) })
	try {
		const a = getMeta("Item"), b = getMeta("Item")
		assert.equal(pending.length, 1)
		window.frappe.session.user = "two"
		const c = getMeta("Item")
		assert.equal(pending.length, 2)
		pending.forEach((item) => item.resolve(response()))
		const [first, second] = await Promise.all([a, b, c])
		first[0].fields[0].label = "changed"
		assert.equal(second[0].fields[0].label, "Original")
		const d = getMeta("Item")
		assert.equal(pending.length, 3)
		pending[2].resolve(response()); await d
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})

test("metadata rejects all subscribers and retries after failure", async () => {
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { location: { host: "site" } }
	let calls = 0
	globalThis.fetch = async () => { calls++; throw new Error("offline") }
	try {
		const results = await Promise.allSettled([getMeta("Retry"), getMeta("Retry")])
		assert.equal(calls, 1)
		assert.ok(results.every((r) => r.status === "rejected"))
		await assert.rejects(getMeta("Retry"), /offline/)
		assert.equal(calls, 2)
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})
