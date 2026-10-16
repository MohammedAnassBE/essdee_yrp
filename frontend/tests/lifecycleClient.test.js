import assert from "node:assert/strict"
import test from "node:test"
import { cancelDoc, getDoc, submitDoc } from "../src/api/frappe.js"

test("lifecycle requests call controller endpoints with the client timestamp", async () => {
	const previousWindow = globalThis.window
	const previousFetch = globalThis.fetch
	const requests = []
	globalThis.window = { csrf_token: "test-csrf" }
	globalThis.fetch = async (url, options) => {
		requests.push({ url, method: options.method, body: JSON.parse(options.body) })
		return { ok: true, status: 200, json: async () => ({ message: { name: "GRN-1" } }) }
	}
	try {
		await submitDoc("YRP Goods Received Note", "GRN-1", "2026-10-16 10:00:00")
		await cancelDoc("YRP Goods Received Note", "GRN-1", "2026-10-16 10:01:00")
		assert.deepEqual(requests.map((entry) => entry.url), ["/api/method/essdee_yrp.api.lifecycle.submit_document", "/api/method/essdee_yrp.api.lifecycle.cancel_document"])
		assert.equal(requests[0].method, "POST")
		assert.equal(requests[1].body.modified, "2026-10-16 10:01:00")
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})

test("expired-session 403 preserves the deep link, while ordinary permission errors stay in place", async () => {
	const previousWindow = globalThis.window
	const previousFetch = globalThis.fetch
	const redirects = []
	globalThis.window = { location: { pathname: "/web/accounts/debits/DEBIT-1", search: "?tab=details", hash: "#notes", assign: (url) => redirects.push(url) } }
	let message = "Login to access this resource"
	globalThis.fetch = async () => ({ ok: false, status: 403, json: async () => ({ exc_type: "PermissionError", message }) })
	try {
		await assert.rejects(getDoc("YRP Debit", "DEBIT-1"), /session has expired/)
		assert.equal(redirects[0], `/login?redirect-to=${encodeURIComponent("/web/accounts/debits/DEBIT-1?tab=details#notes")}`)
		message = "Read permission denied"
		await assert.rejects(getDoc("YRP Debit", "DEBIT-1"), /Read permission denied/)
		assert.equal(redirects.length, 1)
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})
