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
  const a = searchLink("Item", "alpha", { b: 2, a: 1 }), b = searchLink("Item", "alpha", { a: 1, b: 2 })
  assert.equal(pending.length, 1)
  const c = searchLink("Item", "beta", { a: 1, b: 2 }), d = searchLink("Item", "alpha", { a: 1, b: 2 }, 10)
  const e = searchLink("Item", "alpha", { a: 1, b: 2 }, 20, true)
  window.frappe.session.user = "two"
  const f = searchLink("Item", "alpha", { a: 1, b: 2 })
  assert.equal(pending.length, 5)
  pending.forEach((p) => p.resolve(response([{ name: "A", label: "Alpha" }])))
  const [first, second] = await Promise.all([a,b,c,d,e,f])
  first[0].label = "changed"
  assert.equal(second[0].label, "Alpha")
  const again = searchLink("Item", "alpha", { a: 1, b: 2 })
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

test("short link searches reuse a settled result for 30 s per session, arguments and generation", async () => {
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch, oldNow = Date.now
 globalThis.window = { location: { host: "site" }, frappe: { session: { user: "one" } }, csrf_token: "session-a" }
 const pending = []
 globalThis.fetch = () => { const d = deferred(); pending.push(d); return d.promise }
 let now = 1_000_000
 Date.now = () => now
 const settle = async (read, rows) => { pending.at(-1).resolve(response(rows)); return read }
 try {
  api.clearReadCaches()
  const first = await settle(searchLink("Supplier", "", { disabled: 0 }), [{ name: "S-1" }])
  first[0].name = "changed"
  assert.deepEqual(await searchLink("Supplier", "", { disabled: 0 }), [{ name: "S-1" }])
  const failed = searchLinkedDocument("Address", "Supplier", "S-1")
  assert.equal(pending.length, 2)
  pending[1].reject(new Error("offline"))
  await assert.rejects(failed, /offline/)
  const linked = searchLinkedDocument("Address", "Supplier", "S-1")
  assert.equal(pending.length, 3, "failed searches are not kept")
  await settle(linked, [{ name: "ADDR-1" }])
  assert.deepEqual(await searchLinkedDocument("Address", "Supplier", "S-1"), [{ name: "ADDR-1" }])
  assert.equal(pending.length, 3)
  await settle(searchLink("Supplier", "", { disabled: 1 }), [])
  await settle(searchLink("Supplier", "S"), [])
  await searchLink("Supplier", "S")
  await settle(searchLink("Supplier", "S-1"), [])
  assert.equal(pending.length, 6)
  await settle(searchLink("Supplier", "S-1"), [])
  assert.equal(pending.length, 7, "longer queries only share pending requests")
  window.frappe.session.user = "two"
  await settle(searchLink("Supplier", "", { disabled: 0 }), [{ name: "S-2" }])
  window.csrf_token = "session-b"
  await settle(searchLink("Supplier", "", { disabled: 0 }), [{ name: "S-3" }])
  assert.equal(pending.length, 9)
  now += 29_999
  assert.deepEqual(await searchLink("Supplier", "", { disabled: 0 }), [{ name: "S-3" }])
  now += 2
  await settle(searchLink("Supplier", "", { disabled: 0 }), [{ name: "S-4" }])
  assert.equal(pending.length, 10, "results expire after 30 s")
  const save = updateDoc("Supplier", "S-4", { supplier_name: "renamed" })
  pending.at(-1).resolve(response({})); await save
  assert.deepEqual(await settle(searchLink("Supplier", "", { disabled: 0 }), [{ name: "S-5" }]), [{ name: "S-5" }])
  assert.equal(pending.length, 12, "writes drop cached searches")
  await searchLink("Supplier", "", { disabled: 0 })
  api.clearReadCaches()
  await settle(searchLink("Supplier", "", { disabled: 0 }), [])
  assert.equal(pending.length, 13, "logout drops cached searches")
 } finally { Date.now = oldNow; globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test("a short search started before an invalidation cannot fill the cache", async () => {
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch
 globalThis.window = { location: { host: "site" } }
 const pending = []
 globalThis.fetch = () => { const d = deferred(); pending.push(d); return d.promise }
 try {
  api.clearReadCaches()
  const old = searchLink("Lot", "")
  api.invalidatePendingReads()
  pending[0].resolve(response([{ name: "old" }])); await old
  const fresh = searchLink("Lot", "")
  assert.equal(pending.length, 2)
  pending[1].resolve(response([{ name: "fresh" }]))
  assert.deepEqual(await fresh, [{ name: "fresh" }])
  assert.deepEqual(await searchLink("Lot", ""), [{ name: "fresh" }])
  assert.equal(pending.length, 2)
 } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test("callRead shares pending reads without invalidating other readers", async () => {
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch
 globalThis.window = { location: { host: "site" } }
 const pending = []
 globalThis.fetch = () => { const d = deferred(); pending.push(d); return d.promise }
 try {
  api.clearReadCaches()
  const count = getCount("Item", { disabled: 0 })
  const capabilities = [api.callRead("essdee_yrp.planning.web_workspace.get_capabilities"), api.callRead("essdee_yrp.planning.web_workspace.get_capabilities")]
  const sameCount = getCount("Item", { disabled: 0 })
  assert.equal(pending.length, 2)
  pending[0].resolve(response(4)); pending[1].resolve(response({ lots: { read: true } }))
  assert.deepEqual(await Promise.all([count, sameCount]), [4, 4])
  const [first, second] = await Promise.all(capabilities)
  first.lots.read = false
  assert.equal(second.lots.read, true)
 } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test("department capability readers use callRead", async () => {
 const { readFileSync } = await import("node:fs")
 const files = ["accounts", "cutPanelStore", "cuttingWorkspaces", "fabricStore", "finishing", "hr", "merch", "pd", "planning", "purchase", "quality", "sales", "sewing"]
 for (const file of files) {
  const source = readFileSync(new URL(`../src/api/${file}.js`, import.meta.url), "utf8")
  assert.doesNotMatch(source, /callMethod\([^)]*(get_capabilities|get_ipd_list_capabilities|CAPABILITIES_METHOD\))/, file)
  assert.match(source, /callRead\(/, file)
 }
})

test("LinkField drops stale searches locally and invalidates shared reads only on an explicit reset", async () => {
 const { resolve } = await import("node:path")
 const { Vue, findNodes, loadComponent, mountComponent } = await import("../../scripts/helpers/vue_renderer.mjs")
 const autocompleteKeys = await import("../src/components/common/autocompleteKeys.js")
 const tick = async () => { await new Promise((done) => setImmediate(done)); await Vue.nextTick() }
 const searches = []
 let invalidations = 0
 const LinkField = loadComponent(resolve("frontend/src/components/common/LinkField.vue"), {
  "primevue/autocomplete": { inheritAttrs: false, setup: (_, { attrs, expose }) => { expose({ hide() {} }); return () => Vue.h("autocomplete", attrs) } },
  "primevue/button": (attrs) => Vue.h("button", attrs),
  "./autocompleteKeys.js": autocompleteKeys,
  "../../utils/linkTarget.js": { canCreateDoctype: () => false, canReadDoctype: () => false },
  "../../utils/quickEntry.js": { linkCreateValues: () => ({}) },
  "./asyncQuickEntryDialog.js": (attrs) => Vue.h("quick-entry", attrs),
  "./DocumentLink.vue": (attrs) => Vue.h("document-link", attrs),
  "../../api/frappe.js": { invalidatePendingReads() { invalidations++ }, searchLink: (...args) => { const d = deferred(); searches.push({ args, ...d }); return d.promise } },
 })
 const props = Vue.reactive({ doctype: "Supplier", modelValue: "", resetVersion: 0 })
 const root = mountComponent(LinkField, props)
 const autocomplete = () => findNodes(root, (node) => node.type === "autocomplete")[0]
 assert.equal(autocomplete().props.delay, 150)
 const stale = autocomplete().props.onComplete({ query: "S" })
 autocomplete().props["onUpdate:modelValue"]("S-")
 const fresh = autocomplete().props.onComplete({ query: "S-" })
 searches[0].resolve([{ name: "S-OLD" }]); searches[1].resolve([{ name: "S-NEW" }])
 await Promise.all([stale, fresh]); await tick()
 assert.deepEqual(autocomplete().props.suggestions.map((row) => row.name), ["S-NEW"])
 props.modelValue = "S-NEW"; await tick()
 autocomplete().props.onBlur(); await tick()
 assert.equal(invalidations, 0, "typing, selection and blur keep other pending reads shared")
 props.resetVersion += 1; await tick()
 assert.equal(invalidations, 1)
 props.modelValue = ""; await tick()
 assert.equal(invalidations, 1)
})

test("cached link results and metadata resolve on a later task, like a network response", async () => {
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch
 globalThis.window = { location: { host: "site" } }
 globalThis.fetch = async (url) => url.includes("getdoctype")
  ? { ok: true, status: 200, json: async () => ({ docs: [{ name: "Supplier" }] }) }
  : response([{ name: "S-1" }])
 const microtasks = async () => { for (let index = 0; index < 50; index++) await Promise.resolve() }
 try {
  api.clearReadCaches()
  await searchLink("Supplier", "")
  await api.getMeta("Supplier")
  for (const read of [() => searchLink("Supplier", ""), () => api.getMeta("Supplier")]) {
   let settled = false
   const pending = read().then((value) => { settled = true; return value })
   await microtasks()
   assert.equal(settled, false)
   assert.equal((await pending)[0].name.startsWith("S"), true)
  }
 } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch }
})

test("logout, session expiry and a user change in another tab drop cached reads", async () => {
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch, oldDocument = globalThis.document
 const assigned = []
 globalThis.window = { location: { host: "site", pathname: "/web", search: "", hash: "", assign: (url) => assigned.push(url) } }
 globalThis.document = { cookie: "full_name=A; user_id=a%40site" }
 let status = 200
 const urls = []
 globalThis.fetch = async (url) => {
  urls.push(url)
  if (url.includes("getdoctype")) return { ok: true, status: 200, json: async () => ({ docs: [{ name: "Supplier" }] }) }
  return { ok: status === 200, status, json: async () => ({ message: [{ name: "S-1" }] }) }
 }
 const reads = async () => { const before = urls.length; await searchLink("Supplier", ""); await api.getMeta("Supplier"); return urls.length - before }
 try {
  api.clearReadCaches()
  assert.equal(await reads(), 2)
  assert.equal(await reads(), 0)
  document.cookie = "full_name=A; user_id=Guest"
  assert.equal(await reads(), 2, "another tab logged out")
  assert.equal(await reads(), 0)
  await api.logOut()
  assert.deepEqual(assigned, ["/login"])
  assert.equal(await reads(), 2, "logOut drops cached reads")
  status = 401
  await assert.rejects(api.getCount("Supplier"), /session has expired/)
  assert.match(assigned[1], /^\/login\?redirect-to=/)
  status = 200
  assert.equal(await reads(), 2, "an expired session drops cached reads")
 } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch; globalThis.document = oldDocument }
})

test("uploads and file downloads invalidate cached link searches when they start and when they settle", async () => {
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch, oldFile = globalThis.File, oldXhr = globalThis.XMLHttpRequest
 const oldDocument = globalThis.document, oldCreate = URL.createObjectURL, oldFormData = globalThis.FormData
 globalThis.window = { location: { host: "site" }, setTimeout: () => {} }
 globalThis.File = class { constructor(name) { this.name = name } }
 globalThis.FormData = class { append() {} }
 const uploads = []
 globalThis.XMLHttpRequest = class {
  constructor() { this.listeners = {}; this.upload = { addEventListener() {} }; this.status = 200; this.responseText = JSON.stringify({ message: { name: "FILE-1" } }) }
  open() {} setRequestHeader() {} abort() {} addEventListener(name, callback) { this.listeners[name] = callback }
  send() { uploads.push(this) }
 }
 globalThis.document = { cookie: "", createElement: () => ({ click() {} }) }
 URL.createObjectURL = () => "blob:x"
 let searches = 0
 const downloads = []
 globalThis.fetch = (url) => {
  if (url.includes("link_search")) { searches++; return Promise.resolve(response([{ name: `FILE-${searches}` }])) }
  const d = deferred(); downloads.push(d); return d.promise
 }
 const search = () => searchLink("File", "")
 try {
  for (const [name, start, settle] of [
   ["upload load", () => api.uploadFile(new File("a.txt")), () => uploads.at(-1).listeners.load()],
   ["upload error", () => api.uploadFile(new File("a.txt")).catch(() => null), () => uploads.at(-1).listeners.error()],
   ["download", () => api.downloadMethodFile("essdee_yrp.api.export.download", {}), () => downloads.at(-1).resolve({ ok: true, status: 200, headers: { get: () => "" }, blob: async () => new Blob(["x"]) })],
   ["download failure", () => api.downloadMethodFile("essdee_yrp.api.export.download", {}).catch(() => null), () => downloads.at(-1).reject(new Error("offline"))],
  ]) {
   api.clearReadCaches()
   await search()
   const before = searches
   const mutation = start()
   await search()
   assert.equal(searches, before + 1, `${name}: start drops results cached before it`)
   await search()
   assert.equal(searches, before + 1, `${name}: searches during it are cached in their own generation`)
   settle(); await mutation
   await search()
   assert.equal(searches, before + 2, `${name}: settling drops results cached during it`)
  }
 } finally {
  globalThis.window = oldWindow; globalThis.fetch = oldFetch; globalThis.File = oldFile; globalThis.XMLHttpRequest = oldXhr
  globalThis.document = oldDocument; URL.createObjectURL = oldCreate; globalThis.FormData = oldFormData
 }
})

test("a cached read checks the session again before it is delivered", async () => {
 let calls = 0
 const oldWindow = globalThis.window, oldFetch = globalThis.fetch, oldDocument = globalThis.document
 globalThis.window = { location: { host: "site" } }
 globalThis.document = { cookie: "user_id=a" }
 globalThis.fetch = async (url) => {
  const user = `${/user_id=(\w+)/.exec(document.cookie)[1]}-${++calls}`
  return url.includes("getdoctype")
   ? { ok: true, status: 200, json: async () => ({ docs: [{ name: user }] }) }
   : response([{ name: user }])
 }
 try {
  api.clearReadCaches()
  await searchLink("Supplier", ""); await api.getMeta("Supplier")
  const link = searchLink("Supplier", ""), meta = api.getMeta("Supplier")
  document.cookie = "user_id=b"
  assert.equal((await link)[0].name, "b-3")
  assert.equal((await meta)[0].name, "b-4")
  document.cookie = "user_id=a"
  assert.equal((await searchLink("Supplier", ""))[0].name, "a-1")
  const write = searchLink("Supplier", "")
  api.invalidatePendingReads()
  assert.equal((await write)[0].name, "a-5")
 } finally { globalThis.window = oldWindow; globalThis.fetch = oldFetch; globalThis.document = oldDocument }
})
