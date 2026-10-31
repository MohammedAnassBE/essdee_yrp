import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"
import { effectScope, nextTick, ref } from "vue"

globalThis.window = {
	frappe: { boot: { site_name: "site.local" } },
	location: { origin: "http://site.local", protocol: "http:", hostname: "site.local" },
}
globalThis.document = { visibilityState: "visible", addEventListener() {}, removeEventListener() {} }

const realtime = await import("../src/api/realtime.js")
const { useLiveDocument } = await import("../src/composables/useLiveDocument.js")
const { isDocumentDirty, isMissingDocumentError, isStaleDocumentError } = await import("../src/utils/documentLiveState.js")

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
const source = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8")

function fakeSocket() {
	const handlers = new Map()
	const socket = {
		connected: false, active: false, sent: [],
		io: { on() {}, reconnectionAttempts() {}, reconnectionDelayMax() {} },
		on(event, handler) { handlers.set(event, [...(handlers.get(event) || []), handler]) },
		off(event, handler) { handlers.set(event, (handlers.get(event) || []).filter((item) => item !== handler)) },
		connect() { this.active = true },
		emit(...args) { this.sent.push(args) },
		serverEmit(event, ...args) { for (const handler of handlers.get(event) || []) handler(...args) },
		open() { this.connected = true; this.serverEmit("connect") },
	}
	realtime.setSocketClientLoader(async () => ({ io: () => socket }))
	return socket
}

function liveDocument({ dirty = false, reload, rows = null } = {}) {
	const socket = fakeSocket()
	const isDirty = ref(dirty)
	const modified = ref("2026-10-31 10:00:00")
	const calls = { reloads: 0, lists: 0 }
	globalThis.fetch = async () => {
		calls.lists += 1
		return { ok: true, status: 200, json: async () => ({ data: rows ?? [{ name: "T-1", modified: modified.value }] }) }
	}
	const scope = effectScope()
	const live = scope.run(() => useLiveDocument({
		doctype: "ToDo", name: "T-1", localModified: modified, isDirty,
		reload: reload || (async () => { calls.reloads += 1; modified.value = "2026-10-31 10:05:00" }),
	}))
	return { socket, live, isDirty, modified, calls, scope }
}

test("stale and missing document errors are recognised", () => {
	assert.equal(isStaleDocumentError({ exc_type: "TimestampMismatchError", message: "x" }), true)
	assert.equal(isStaleDocumentError(new Error("Error: T-1 (ToDo) has been modified after you have opened it")), true)
	assert.equal(isStaleDocumentError("DC-1 changed after you opened it. Refresh and try again."), true)
	assert.equal(isStaleDocumentError(new Error("Quantity is required")), false)
	assert.equal(isMissingDocumentError({ status: 404 }), true)
	assert.equal(isMissingDocumentError({ exc_type: "DoesNotExistError" }), true)
	assert.equal(isMissingDocumentError({ status: 417 }), false)
})

test("dirty check compares fields and child rows, treating empty values alike", () => {
	const clean = { name: "T-1", description: "a", priority: null, items: [{ qty: 1, item: "X" }] }
	assert.equal(isDocumentDirty({ ...clean, priority: "", __unsaved: 1 }, clean), false)
	assert.equal(isDocumentDirty({ ...clean, description: "b" }, clean), true)
	assert.equal(isDocumentDirty({ ...clean, items: [{ qty: 2, item: "X" }] }, clean), true)
	assert.equal(isDocumentDirty({ ...clean, items: [...clean.items, { qty: 1 }] }, clean), true)
	assert.equal(isDocumentDirty({ ...clean, items: [{ qty: "1", item: "X", __islocal: 1 }] }, clean), false)
})

test("a remote save reloads a clean document silently", async () => {
	const { socket, live, calls, scope } = liveDocument()
	await flush()
	socket.open()
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "2026-10-31 10:00:00" })
	assert.equal(calls.reloads, 0, "own echo is ignored")
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "2026-10-31 10:05:00" })
	await flush()
	assert.equal(calls.reloads, 1)
	assert.equal(live.state.value, "")
	scope.stop()
})

test("a remote save on a dirty document shows the modified state and keeps edits until Reload", async () => {
	const { socket, live, isDirty, calls, scope } = liveDocument({ dirty: true })
	await flush()
	socket.open()
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "2026-10-31 10:05:00" })
	await flush()
	assert.deepEqual([live.state.value, live.remoteModified.value, calls.reloads], ["modified", "2026-10-31 10:05:00", 0])
	isDirty.value = false
	await live.refresh()
	assert.deepEqual([live.state.value, calls.reloads], ["", 1])
	scope.stop()
})

test("a stale save rejection becomes the modified state instead of an error", () => {
	const { live, scope } = liveDocument({ dirty: true })
	assert.equal(live.handleSaveError({ exc_type: "TimestampMismatchError" }), true)
	assert.equal(live.state.value, "modified")
	assert.equal(live.handleSaveError(new Error("Missing qty")), false)
	scope.stop()
})

test("a delete is detected from list_update and from a 404 reload", async (t) => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	const deleted = liveDocument({ rows: [] })
	await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
	deleted.socket.open()
	deleted.socket.serverEmit("list_update", { doctype: "ToDo", name: "T-1", user: "other@test" })
	t.mock.timers.tick(600)
	for (let index = 0; index < 10; index += 1) await Promise.resolve()
	assert.equal(deleted.calls.lists, 1)
	assert.equal(deleted.live.state.value, "deleted")
	deleted.scope.stop()
	t.mock.timers.reset()

	const missing = liveDocument({ reload: async () => { throw Object.assign(new Error("Not found"), { status: 404 }) } })
	await missing.live.refresh()
	assert.equal(missing.live.state.value, "deleted")
	missing.scope.stop()
})

test("an unchanged list_update for this document does nothing", async (t) => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	const { socket, live, calls, scope } = liveDocument()
	await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
	socket.open()
	socket.serverEmit("list_update", { doctype: "ToDo", name: "T-1", user: "me@test" })
	t.mock.timers.tick(600)
	for (let index = 0; index < 10; index += 1) await Promise.resolve()
	assert.deepEqual([calls.lists, calls.reloads, live.state.value], [1, 0, ""])
	scope.stop()
	await nextTick()
})

test("FormView wires live updates, sends modified on update and keeps edits on remote change", () => {
	const formView = source("../src/components/common/FormView.vue")
	assert.match(formView, /useLiveDocument\(\{[\s\S]*localModified: \(\) => form\.modified[\s\S]*isBusy: \(\) => saving\.value \|\| loading\.value/)
	assert.match(formView, /values\.modified = form\.modified/)
	assert.match(formView, /<DocumentLiveBar/)
	assert.match(formView, /<DocumentSaveState/)
	const save = formView.slice(formView.indexOf("async function save()"), formView.indexOf("defineExpose"))
	assert.ok(save.indexOf("replaceForm(saved || form)") < save.indexOf("saving.value = false"), "modified is updated before saving clears")
	assert.match(save, /live\.handleSaveError\(reason\)/)
})

test("an editor save hands 'Saved' over to the next document page for a minute", async () => {
	const { withSavedHandoff, takeSavedHandoff } = await import("../src/utils/documentLiveState.js")
	const location = withSavedHandoff({ name: "lot", state: { back: "/lots" } })
	assert.equal(location.state.back, "/lots")
	window.history = { state: location.state }
	assert.equal(takeSavedHandoff(), location.state.documentSavedAt)
	window.history = { state: { documentSavedAt: Date.now() - 120_000 } }
	assert.equal(takeSavedHandoff(), null)
	delete window.history
	for (const path of ["purchase/lot/useLotEditor.js", "planning/lot/useLotEditor.js", "merch/lot/useMerchLotEditor.js"]) {
		assert.match(source(`../src/departments/${path}`), /router\.replace\(withSavedHandoff\(viewTarget/)
	}
})

const settle = async () => { for (let index = 0; index < 20; index += 1) await Promise.resolve() }

function formViewReload() {
	const formView = source("../src/components/common/FormView.vue")
	const body = formView.slice(formView.indexOf("async function reloadInBackground("), formView.indexOf("function buildInitialValues("))
	const pendingDocs = []
	const state = { form: { name: "T-1", description: "mine", modified: "A" }, replaced: 0, saving: { value: false } }
	const getDoc = () => new Promise((resolve) => pendingDocs.push(resolve))
	const factory = new Function("getDoc", "props", "documentName", "saving", "state", "isDirty", `
		let loadSequence = 0, editRevision = 0, saveGeneration = 0
		const form = state.form
		const replaceForm = (value) => { state.replaced += 1; Object.assign(form, value) }
		const cleanDocument = {}, fieldErrors = {}, childErrors = {}, error = {}, meta = {}
		const clone = (value) => JSON.parse(JSON.stringify(value)), clearObject = () => {}, emit = () => {}
		${body}
		return { reloadInBackground, edit: () => { editRevision += 1 }, save: () => { saveGeneration += 1 } }`)
	state.dirty = { value: false }
	const api = factory(getDoc, { doctype: "ToDo" }, { value: "T-1" }, state.saving, state, state.dirty)
	return { ...api, state, resolveDoc: (doc) => pendingDocs.shift()(doc) }
}

test("#1 FormView: a background response never overwrites edits or a newer save made while it was in flight", async () => {
	const edited = formViewReload()
	const editedRun = edited.reloadInBackground()
	edited.edit()
	edited.resolveDoc({ name: "T-1", description: "theirs", modified: "B" })
	assert.equal(await editedRun, false, "edited meanwhile: not applied")
	assert.deepEqual([edited.state.form.description, edited.state.replaced], ["mine", 0])

	const saved = formViewReload()
	const savedRun = saved.reloadInBackground()
	saved.save()
	saved.state.form.modified = "C"
	saved.resolveDoc({ name: "T-1", description: "old", modified: "B" })
	assert.equal(await savedRun, false, "a save started meanwhile: the older response is dropped")
	assert.equal(saved.state.form.modified, "C")

	const discarded = formViewReload()
	discarded.state.dirty.value = true
	const discardRun = discarded.reloadInBackground({ discard: true })
	discarded.resolveDoc({ name: "T-1", description: "theirs", modified: "B" })
	await discardRun
	assert.equal(discarded.state.form.description, "theirs", "Reload after the discard confirm drops the earlier edits")
})

test("#1 a declined background reload keeps edits and shows the bar", async () => {
	const { socket, live, isDirty, calls, scope } = liveDocument({ reload: async () => { calls.reloads += 1; isDirty.value = true; return false } })
	await flush()
	socket.open()
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "2026-10-31 10:05:00" })
	await settle()
	assert.deepEqual([calls.reloads, live.state.value], [1, "modified"])
	scope.stop()
})

test("#1 editors refuse stale background responses", () => {
	const checks = {
		"../src/departments/fabric-store/PurchaseOrderEditor.vue": /saves !== saveGeneration \|\| busy\.value \|\| draftFingerprint\(\) !== draftAtStart \|\| \(!discard && dirty\.value\)\) return false/,
		"../src/departments/fabric-store/WorkOrderEditor.vue": /saves !== saveGeneration \|\| busy\.value \|\| draftFingerprint\(\) !== draftAtStart \|\| \(!discard && dirty\.value\)\) return false/,
		"../src/departments/purchase/lot/useLotEditor.js": /mutations !== mutationSequence \|\| acting\.value \|\| signature\.value !== draftAtStart \|\| \(!discard && isDirty\.value\)\) return false/,
		"../src/departments/planning/lot/useLotEditor.js": /mutations !== mutationSequence \|\| acting\.value \|\| signature\.value !== draftAtStart \|\| \(!discard && isDirty\.value\)\) return false/,
		"../src/departments/merch/lot/useMerchLotEditor.js": /mutations !== mutationSequence \|\| acting\.value \|\| signature\.value !== draftAtStart \|\| \(!discard && isDirty\.value\)\) return false/,
		"../src/departments/merch/ipd/useIpdEditor.js": /acting\.value \|\| stableStringify\(draft\) !== draftAtStart \|\| \(!discard && isDirty\.value\)\) return false/,
		"../src/departments/fabric-store/DeliveryChallanWorkspace.vue": /actions !== actionSequence \|\| acting\.value \|\| draftFingerprint\(\) !== draftAtStart \|\| \(!discard && dirty\.value\)\) return false/,
		"../src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue": /actions !== actionSequence \|\| acting\.value \|\| draftFingerprint\(\) !== draftAtStart \|\| \(!discard && dirty\.value\)\) return false/,
	}
	for (const [path, pattern] of Object.entries(checks)) assert.match(source(path), pattern, path)
})

test("#3 a change arriving during a reload gets its own pass; nothing is dropped", async () => {
	const releases = []
	const { socket, live, modified, calls, scope } = liveDocument({
		reload: () => new Promise((resolve) => { calls.reloads += 1; releases.push(resolve) }),
	})
	await flush()
	socket.open()
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "B" })
	await settle()
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "C" })
	modified.value = "B"
	releases.shift()()
	await settle()
	assert.equal(calls.reloads, 2, "the stamp that arrived mid-reload triggers a second reload")
	modified.value = "C"
	releases.shift()()
	await settle()
	assert.deepEqual([calls.reloads, live.state.value, live.remoteModified.value], [2, "", ""])
	scope.stop()
})

test("#3 a delete check that arrives while busy runs once busy clears", async (t) => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	const socket = fakeSocket()
	const busy = ref(true)
	let lists = 0
	globalThis.fetch = async () => { lists += 1; return { ok: true, status: 200, json: async () => ({ data: [] }) } }
	const scope = effectScope()
	const live = scope.run(() => useLiveDocument({ doctype: "ToDo", name: "T-1", localModified: "A", isBusy: busy, reload: async () => {} }))
	await settle()
	socket.open()
	socket.serverEmit("list_update", { doctype: "ToDo", name: "T-1", user: "other@test" })
	t.mock.timers.tick(600)
	await settle()
	assert.deepEqual([lists, live.state.value], [0, ""], "held while saving")
	busy.value = false
	await nextTick()
	await settle()
	assert.deepEqual([lists, live.state.value], [1, "deleted"])
	scope.stop()
})

test("#4 after a reconnect the document reconciles with the server, respecting dirty", async () => {
	const { socket, live, isDirty, modified, calls, scope } = liveDocument({ dirty: true })
	await flush()
	socket.open()
	globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({ data: [{ name: "T-1", modified: "2026-10-31 11:00:00" }] }) })
	socket.connected = false
	socket.serverEmit("disconnect", "transport close")
	socket.open()
	await settle()
	assert.deepEqual([live.state.value, calls.reloads], ["modified", 0], "dirty: the bar, edits kept")
	isDirty.value = false
	await nextTick()
	await settle()
	assert.equal(calls.reloads, 1, "once clean, the missed change reloads silently")
	assert.equal(modified.value, "2026-10-31 10:05:00")
	scope.stop()
})

test("#6 nothing changes after the page is gone", async () => {
	let resolveList
	const { socket, live, calls, scope } = liveDocument()
	globalThis.fetch = () => new Promise((resolve) => { resolveList = resolve })
	await flush()
	socket.open()
	socket.connected = false
	socket.serverEmit("disconnect", "transport close")
	socket.open()
	await settle()
	scope.stop()
	resolveList({ ok: true, status: 200, json: async () => ({ data: [] }) })
	await settle()
	assert.deepEqual([live.state.value, calls.reloads], ["", 0])
	assert.match(source("../src/composables/useLiveDocument.js"), /checkVersion\.cancel\(\)/)
	assert.match(source("../src/components/common/FormView.vue"), /onScopeDispose\(\(\) => \{ loadSequence \+= 1 \}\)/)
})

test("#2 embedded and page workspaces share one live state, bar and delete detection", () => {
	const shell = source("../src/departments/fabric-store/FabricDocumentWorkspace.vue")
	assert.doesNotMatch(shell, /useDocRealtime|remoteChange|presentation === 'page' && !loading/)
	assert.match(shell, /name: \(\) => record\.value\.name \|\| "",/)
	assert.equal(shell.match(/<DocumentLiveBar/g).length, 1)
})

test("#9 toolbar Refresh takes the background path after a discard confirm", () => {
	const shell = source("../src/departments/fabric-store/FabricDocumentWorkspace.vue")
	assert.match(shell, /aria-label="Refresh"[\s\S]*?@click="requestRefresh"/)
	const refresh = shell.slice(shell.indexOf("function requestRefresh()"), shell.indexOf("function confirmRefresh()"))
	assert.match(refresh, /if \(!props\.liveReload\) return emit\("reload"\)/)
	assert.match(refresh, /if \(props\.dirty\) refreshConfirmVisible\.value = true/)
	assert.match(refresh, /else live\.refresh\(\{ discard: false \}\)/)
	assert.match(shell.slice(shell.indexOf("function confirmRefresh()")), /live\.refresh\(\)/)
	assert.match(source("../src/departments/merch/ipd/IpdEditor.vue"), /:live-reload="refresh"/)
	for (const path of ["purchase/lot/LotEditor.vue", "planning/lot/LotEditor.vue", "merch/lot/MerchLotEditor.vue"]) {
		assert.match(source(`../src/departments/${path}`), /:live-reload="refresh"/, path)
	}
})

test("recheck #1 failed reloads back off (2 s, 5 s, 15 s) and then wait for the next trigger", async (t) => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	const { socket, live, calls, scope } = liveDocument({ reload: async () => { calls.reloads += 1; throw Object.assign(new Error("Server down"), { status: 502 }) } })
	await settle()
	socket.open()
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "B" })
	await settle()
	assert.equal(calls.reloads, 1, "no immediate retry")
	for (const [delay, expected] of [[1_999, 1], [1, 2], [5_000, 3], [15_000, 4], [60_000, 4], [600_000, 4]]) {
		t.mock.timers.tick(delay)
		await settle()
		assert.equal(calls.reloads, expected, `after +${delay} ms`)
	}
	assert.equal(live.state.value, "", "a clean page shows no bar for a failed silent reload")
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "C" })
	await settle()
	assert.equal(calls.reloads, 5, "a new event tries again")
	scope.stop()
})

test("recheck #1 a declined reload waits for busy → idle instead of looping", async () => {
	const socket = fakeSocket()
	const busy = ref(false)
	let reloads = 0
	const scope = effectScope()
	scope.run(() => useLiveDocument({ doctype: "ToDo", name: "T-1", localModified: "A", isBusy: busy, reload: async () => { reloads += 1; return reloads > 2 ? undefined : false } }))
	await settle()
	socket.open()
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "B" })
	for (let index = 0; index < 5; index += 1) await settle()
	assert.equal(reloads, 1, "declined once, no retry storm")
	busy.value = true
	await nextTick()
	busy.value = false
	await nextTick()
	await settle()
	assert.equal(reloads, 2, "one retry per transition")
	scope.stop()
})

test("recheck #1 a background response loses to edits made after a discard confirm", async () => {
	const discarded = formViewReload()
	discarded.state.dirty.value = true
	const run = discarded.reloadInBackground({ discard: true })
	discarded.edit()
	discarded.resolveDoc({ name: "T-1", description: "theirs", modified: "B" })
	assert.equal(await run, false)
	assert.equal(discarded.state.form.description, "mine")
})

test("recheck #2 toolbar Refresh on a clean document does not discard", () => {
	const shell = source("../src/departments/fabric-store/FabricDocumentWorkspace.vue")
	const refresh = shell.slice(shell.indexOf("function requestRefresh()"), shell.indexOf("function confirmRefresh()"))
	assert.match(refresh, /else live\.refresh\(\{ discard: false \}\)/)
})

test("recheck #4 Lot pages drop refresh responses after unmount", () => {
	for (const path of ["purchase/lot/LotPage.vue", "planning/lot/LotPage.vue"]) {
		const page = source(`../src/departments/${path}`)
		assert.match(page, /onBeforeUnmount\(\(\) => \{ loadSequence \+= 1 \}\)/, path)
		assert.match(page.slice(page.indexOf("async function refreshInBackground")), /isCurrentRecordRequest\(requestedName, props\.lotId, sequence, loadSequence\)\) workspace\.value = payload/, path)
	}
})

test("recheck: a deleted document cannot be saved, submitted or cancelled by shortcut or click", async () => {
	const { Vue, loadComponent, mountComponent, findNodes } = await import("../../scripts/helpers/vue_renderer.mjs")
	const { DOCUMENT_DELETED_KEY } = await import("../src/utils/documentLiveState.js")
	let shortcuts = null
	const strip = loadComponent(new URL("../src/components/documents/DocumentActionStrip.vue", import.meta.url).pathname, {
		"primevue/button": (props) => Vue.h("button", props, props.label), "primevue/menu": (props) => Vue.h("menu", props),
		"../../composables/useDocumentShortcuts.js": { useDocumentShortcuts: (options) => { shortcuts = options } },
	})
	const deleted = Vue.ref(false)
	const saves = []
	const actions = [{ key: "save", label: "Save", primary: true, shortcut: "save", command: () => saves.push(1) }]
	const root = mountComponent({ setup() { Vue.provide(DOCUMENT_DELETED_KEY, deleted); return () => Vue.h(strip, { actions }) } })
	assert.equal(shortcuts.canSave(), true)
	deleted.value = true
	assert.equal(shortcuts.canSave(), false)
	shortcuts.save()
	findNodes(root, (node) => node.type === "button" && node.props.label === "Save")[0].props.onClick()
	assert.deepEqual(saves, [])
	const shell = source("../src/departments/fabric-store/FabricDocumentWorkspace.vue")
	assert.match(shell, /provide\(DOCUMENT_DELETED_KEY, isDeleted\)/)
	for (const path of ["DeliveryChallanWorkspace.vue", "GoodsReceivedNoteWorkspace.vue"]) {
		const workspace = source(`../src/departments/fabric-store/${path}`)
		assert.match(workspace, /async function save\(submit\) \{\n\tif \(liveState\.value === "deleted"\) return/, path)
		assert.match(workspace, /@live-state="liveState = \$event"/, path)
	}
})
