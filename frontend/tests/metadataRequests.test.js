import assert from "node:assert/strict"
import test from "node:test"
import { clearReadCaches, getMeta, invalidatePendingReads } from "../src/api/frappe.js"

const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r }); return { promise, resolve } }
const response = (doctype = "Item") => ({ ok: true, status: 200, json: async () => ({ docs: [{ name: doctype, fields: [{ label: "Original" }] }] }) })

test("metadata is shared per session identity, returned as copies and kept after it settles", async () => {
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { location: { host: "site" }, frappe: { session: { user: "one" } } }
	const pending = []
	globalThis.fetch = () => { const item = deferred(); pending.push(item); return item.promise }
	try {
		clearReadCaches()
		const a = getMeta("Item"), b = getMeta("Item")
		assert.equal(pending.length, 1)
		window.frappe.session.user = "two"
		const c = getMeta("Item")
		assert.equal(pending.length, 2)
		pending.forEach((item) => item.resolve(response()))
		const [first, second] = await Promise.all([a, b, c])
		first[0].fields[0].label = "changed"
		assert.equal(second[0].fields[0].label, "Original")
		invalidatePendingReads()
		const settled = await getMeta("Item")
		assert.equal(pending.length, 2, "writes do not drop metadata")
		assert.equal(settled[0].fields[0].label, "Original")
		clearReadCaches()
		const d = getMeta("Item")
		assert.equal(pending.length, 3, "logout drops metadata")
		pending[2].resolve(response()); await d
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})

test("metadata keeps the 20 most recently used doctypes", async () => {
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { location: { host: "site" } }
	let calls = 0
	globalThis.fetch = async (url) => { calls++; return response(new URL(url, "http://site").searchParams.get("doctype")) }
	try {
		clearReadCaches()
		for (let index = 0; index < 20; index++) await getMeta(`Doctype ${index}`)
		await getMeta("Doctype 0")
		await getMeta("Doctype 20")
		assert.equal(calls, 21)
		assert.equal((await getMeta("Doctype 0"))[0].name, "Doctype 0")
		assert.equal(calls, 21)
		await getMeta("Doctype 1")
		assert.equal(calls, 22)
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})

test("metadata rejects all subscribers and retries after failure", async () => {
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { location: { host: "site" } }
	let calls = 0
	globalThis.fetch = async () => { calls++; throw new Error("offline") }
	try {
		clearReadCaches()
		const results = await Promise.allSettled([getMeta("Retry"), getMeta("Retry")])
		assert.equal(calls, 1)
		assert.ok(results.every((r) => r.status === "rejected"))
		await assert.rejects(getMeta("Retry"), /offline/)
		assert.equal(calls, 2)
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})
