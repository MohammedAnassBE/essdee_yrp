import assert from "node:assert/strict"
import test from "node:test"
import { ref } from "vue"
import { getDuplicateValues } from "../src/api/frappe.js"
import { loadDuplicateValues, runDuplicate, useDuplicateAction } from "../src/composables/useDuplicateAction.js"

function withFetch(message, run) {
	const previousWindow = globalThis.window
	const previousFetch = globalThis.fetch
	const requests = []
	globalThis.window = { csrf_token: "test-csrf" }
	globalThis.fetch = async (url, options) => {
		requests.push({ url, body: JSON.parse(options.body) })
		return { ok: true, status: 200, json: async () => ({ message }) }
	}
	return run(requests).finally(() => { globalThis.window = previousWindow; globalThis.fetch = previousFetch })
}

test("getDuplicateValues calls the duplicate endpoint", () => withFetch({ doctype: "YRP Lot", docstatus: 0 }, async (requests) => {
	const values = await getDuplicateValues("YRP Lot", "LOT-1")
	assert.deepEqual(values, { doctype: "YRP Lot", docstatus: 0 })
	assert.equal(requests[0].url, "/api/method/essdee_yrp.api.duplicate.get_duplicate_values")
	assert.deepEqual(requests[0].body, { doctype: "YRP Lot", name: "LOT-1" })
}))

test("duplicate action is a menu-only clone action that opens the new route", () => {
	const pushes = []
	const router = { push: (location) => pushes.push(location) }
	const busy = ref(true)
	const action = useDuplicateAction({ canCreate: ref(true), newRouteName: "lot-new", name: () => "LOT-1", busy, router })
	assert.equal(action.value.key, "duplicate")
	assert.equal(action.value.label, "Duplicate")
	assert.equal(action.value.icon, "pi pi-clone")
	assert.equal(action.value.menuOnly, true)
	assert.equal(action.value.disabled, true)
	busy.value = false
	assert.equal(action.value.disabled, false)
	action.value.command()
	assert.deepEqual(pushes, [{ name: "lot-new", query: { duplicate_from: "LOT-1" } }])
})

test("duplicate action is hidden without create permission or a saved name", () => {
	const router = { push() {} }
	assert.equal(useDuplicateAction({ canCreate: false, newRouteName: "lot-new", name: "LOT-1", router }).value, null)
	assert.equal(useDuplicateAction({ canCreate: true, newRouteName: "lot-new", name: "", router }).value, null)
})

test("runDuplicate honours a custom query key", () => {
	const pushes = []
	runDuplicate({ push: (location) => pushes.push(location) }, { newRouteName: "po-new", name: "PO-1", queryKey: "copy" })
	assert.deepEqual(pushes, [{ name: "po-new", query: { copy: "PO-1" } }])
})

test("loadDuplicateValues returns null without the query and values with it", () => withFetch({ doctype: "YRP Lot", title: "A" }, async (requests) => {
	assert.equal(await loadDuplicateValues("YRP Lot", { query: {} }), null)
	assert.equal(requests.length, 0)
	assert.deepEqual(await loadDuplicateValues("YRP Lot", { query: { duplicate_from: "LOT-1" } }), { doctype: "YRP Lot", title: "A" })
	assert.deepEqual(requests[0].body, { doctype: "YRP Lot", name: "LOT-1" })
}))
