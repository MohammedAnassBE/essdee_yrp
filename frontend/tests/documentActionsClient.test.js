import assert from "node:assert/strict"
import test from "node:test"
import { deleteDoc, getDocPermissions, getPrintOptions } from "../src/api/frappe.js"

test("document APIs use Frappe permissions, delete, and print options endpoints", async () => {
	const previousWindow = globalThis.window
	const previousFetch = globalThis.fetch
	const requests = []
	const options = { formats: ["Standard"], default_format: "Standard", letter_heads: [], default_letter_head: "" }
	globalThis.window = { csrf_token: "test-csrf" }
	globalThis.fetch = async (url, init) => {
		requests.push({ url, method: init.method, args: init.body ? JSON.parse(init.body) : undefined })
		return { ok: true, status: 200, json: async () => ({ message: url.includes("get_doc_permissions") ? { permissions: { delete: 1 } } : options }) }
	}
	try {
		assert.deepEqual(await getDocPermissions("Test Doc", "DOC/1"), { delete: 1 })
		await deleteDoc("Test Doc", "DOC/1")
		assert.deepEqual(await getPrintOptions("Test Doc", "DOC/1"), options)
		assert.deepEqual(requests, [
			{ url: "/api/method/frappe.client.get_doc_permissions?doctype=Test+Doc&docname=DOC%2F1", method: "GET", args: undefined },
			{ url: "/api/method/frappe.client.delete", method: "POST", args: { doctype: "Test Doc", name: "DOC/1" } },
			{ url: "/api/method/essdee_yrp.api.print.get_print_options?doctype=Test+Doc&name=DOC%2F1", method: "GET", args: undefined },
		])
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})

test("permission, print and delete calls keep session metadata; logout drops it", async () => {
	const { clearReadCaches, getMeta } = await import("../src/api/frappe.js")
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { location: { host: "document-actions" }, csrf_token: "token" }
	const metadata = []
	globalThis.fetch = (url) => {
		if (url.includes("getdoctype")) return new Promise(resolve => metadata.push(resolve))
		return Promise.resolve({ ok: true, status: 200, json: async () => ({ message: { permissions: { print: 1 } } }) })
	}
	clearReadCaches()
	try {
		const a = getMeta("Pending")
		await getDocPermissions("Pending", "DOC-1")
		await getPrintOptions("Pending", "DOC-1")
		const b = getMeta("Pending")
		await deleteDoc("Pending", "DOC-1")
		const c = getMeta("Pending")
		assert.equal(metadata.length, 1)
		clearReadCaches()
		const d = getMeta("Pending")
		assert.equal(metadata.length, 2)
		metadata.forEach(resolve => resolve({ ok: true, status: 200, json: async () => ({ docs: [] }) }))
		await Promise.all([a, b, c, d])
	} finally { clearReadCaches(); globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})
