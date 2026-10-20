import assert from "node:assert/strict"
import test from "node:test"
import { getCount, getList } from "../src/api/frappe.js"

test("getList keeps short GETs and posts large variant filters with identical arguments", async () => {
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { csrf_token: "token" }
	const requests = []
	globalThis.fetch = async (url, options) => {
		requests.push({ url, options })
		return { ok: true, status: 200, json: async () => options.method === "POST" ? { message: [{ name: "POST" }] } : { data: [{ name: "GET" }] } }
	}
	try {
		assert.deepEqual(await getList("YRP Stock Entry"), [{ name: "GET" }])
		assert.equal(requests[0].options.method, "GET")
		const filters = [["Detail", "item", "in", Array.from({ length: 1301 }, (_, i) => `Variant-${i}`)]]
		assert.deepEqual(await getList("YRP Stock Entry", { fields: ["name", "posting_date"], filters, orderBy: "name asc", start: 20, pageLength: 50 }), [{ name: "POST" }])
		assert.equal(requests[1].url, "/api/method/frappe.client.get_list")
		assert.equal(requests[1].options.method, "POST")
		assert.deepEqual(JSON.parse(requests[1].options.body), { doctype: "YRP Stock Entry", fields: ["name", "posting_date"], filters, order_by: "name asc", limit_start: 20, limit_page_length: 50 })
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})

test("getList groups by parent name and getCount counts distinct parents when asked", async () => {
	const previousWindow = globalThis.window, previousFetch = globalThis.fetch
	globalThis.window = { csrf_token: "token" }
	const requests = []
	globalThis.fetch = async (url, options) => {
		requests.push({ url, options })
		return { ok: true, status: 200, json: async () => options.method === "POST" ? { message: 3 } : { data: [] } }
	}
	try {
		await getList("YRP Stock Entry", { filters: [["Detail", "item", "=", "A"]], groupBy: "`tabYRP Stock Entry`.`name`" })
		assert.equal(new URL(requests[0].url, "http://x").searchParams.get("group_by"), "`tabYRP Stock Entry`.`name`")
		assert.equal(await getCount("YRP Stock Entry", [["Detail", "item", "=", "B"]], { distinct: true }), 3)
		assert.equal(JSON.parse(requests[1].options.body).distinct, true)
	} finally { globalThis.window = previousWindow; globalThis.fetch = previousFetch }
})
