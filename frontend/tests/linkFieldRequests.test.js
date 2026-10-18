import assert from "node:assert/strict"
import test from "node:test"
import * as api from "../src/api/frappe.js"
const { callMethod, updateDoc, getCount, getActiveWorkflow, searchLink, searchLinkedDocument } = api

const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
const response = (message) => ({ ok: true, status: 200, json: async () => ({ message }) })

test("search shares only complete identical pending arguments and detaches results", async () => {
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch
 globalThis.window = { location: { host: "site" }, frappe: { session: { user: "one" } } }
 const pending = []
 globalThis.fetch = (url, options) => { const d = deferred(); pending.push({ ...d, url, args: JSON.parse(options.body) }); return d.promise }
 try {
  const a = searchLink("Item", "a", { b: 2, a: 1 }), b = searchLink("Item", "a", { a: 1, b: 2 })
  assert.equal(pending.length, 1)
  const c = searchLink("Item", "b", { a: 1, b: 2 }), d = searchLink("Item", "a", { a: 1, b: 2 }, 10)
  const e = searchLink("Item", "a", { a: 1, b: 2 }, 20, true)
  window.frappe.session.user = "two"
  const f = searchLink("Item", "a", { a: 1, b: 2 })
  assert.equal(pending.length, 5)
  pending.forEach((p) => p.resolve(response([{ name: "A", label: "Alpha" }])))
  const [first, second] = await Promise.all([a,b,c,d,e,f])
  first[0].label = "changed"
  assert.equal(second[0].label, "Alpha")
  const again = searchLink("Item", "a", { a: 1, b: 2 })
  assert.equal(pending.length, 6)
  pending[5].resolve(response([])); await again
 } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test("relationships isolate suppliers, endpoints, errors and retries", async () => {
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch
 globalThis.window = { location: { host: "site" } }
 const pending = []
 globalThis.fetch = () => { const d = deferred(); pending.push(d); return d.promise }
 try {
  const a = searchLinkedDocument("Address", "Supplier", "A"), b = searchLinkedDocument("Address", "Supplier", "A")
  const c = searchLinkedDocument("Address", "Supplier", "B"), d = searchLink("Address")
  assert.equal(pending.length, 3)
  pending[0].reject(new Error("offline")); pending[1].resolve(response([{ name: "B" }])); pending[2].resolve(response([]))
  const results = await Promise.allSettled([a,b,c,d])
  assert.equal(results[0].status, "rejected"); assert.equal(results[1].status, "rejected")
  assert.deepEqual(results[2].value, [{ name: "B" }])
  const retry = searchLinkedDocument("Address", "Supplier", "A")
  assert.equal(pending.length, 4); pending[3].resolve(response([])); await retry
  assert.deepEqual(await searchLinkedDocument("Address", "Supplier", ""), [])
 } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test("identical pending counts and workflow calls share work without keeping settled results", async () => {
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch
 globalThis.window = { location: { host: "site" } }
 const pending = []
 globalThis.fetch = () => { const d = deferred(); pending.push(d); return d.promise }
 try {
  const counts = [getCount("Item", { disabled: 0 }), getCount("Item", { disabled: 0 })]
  const workflows = [getActiveWorkflow("Item"), getActiveWorkflow("Item")]
  assert.equal(pending.length, 2)
  pending[0].resolve(response(7)); pending[1].resolve(response({ name: "flow" }))
  assert.deepEqual(await Promise.all(counts), [7,7]); await Promise.all(workflows)
 } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})


test("completed writes and explicit picker resets cannot share older pending reads", async () => {
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch
 globalThis.window = { location: { host: "site" } }
 const pending = []
 globalThis.fetch = () => { const d = deferred(); pending.push(d); return d.promise }
 try {
  const oldCount = getCount("Item")
  const write = callMethod("essdee_yrp.api.bulk_edit.bulk_update_field", { doctype: "Item" })
  pending[1].resolve(response({})); await write
  const newCount = getCount("Item")
  assert.equal(pending.length, 3)
  pending[0].resolve(response(1)); await oldCount
  const sameNewCount = getCount("Item")
  assert.equal(pending.length, 3)
  pending[2].resolve(response(2)); assert.deepEqual(await Promise.all([newCount, sameNewCount]), [2,2])
  const beforeSave = searchLink("Item")
  const save = updateDoc("Item", "A", { item_name: "changed" })
  pending[4].resolve(response({})); await save
  const afterSave = searchLink("Item")
  assert.equal(pending.length, 6)
  api.invalidatePendingReads()
  const afterReset = searchLink("Item")
  assert.equal(pending.length, 7)
  pending[3].resolve(response([{ name: "old" }]))
  pending[5].resolve(response([{ name: "saved" }]))
  pending[6].resolve(response([{ name: "reset" }]))
  const results = await Promise.all([beforeSave, afterSave, afterReset])
  assert.equal(results[2][0].name, "reset")
 } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test("LinkField cancellation used by resetVersion starts a fresh search generation", async () => {
 const { readFileSync } = await import("node:fs")
 const source = readFileSync(new URL("../src/components/common/LinkField.vue", import.meta.url), "utf8")
 const code = source.slice(source.indexOf("function cancelSearch()"), source.indexOf("function setValidation("))
 const cancel = new Function("invalidatePendingReads", "input", "suggestions", "searching", `let requestSequence = 0, suggestionSequence = 0; ${code}; return cancelSearch`)(api.invalidatePendingReads, { value: null }, { value: [] }, { value: true })
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch
 globalThis.window = { location: { host: "site" } }
 const pending = []
 globalThis.fetch = () => { const d = deferred(); pending.push(d); return d.promise }
 try {
  const old = searchLink("Item", "same")
  cancel()
  const fresh = searchLink("Item", "same")
  assert.equal(pending.length, 2)
  pending[0].resolve(response([{ name: "old" }])); pending[1].resolve(response([{ name: "fresh" }]))
  assert.equal((await fresh)[0].name, "fresh"); await old
 } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})
