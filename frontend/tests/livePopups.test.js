import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { computed, effectScope, reactive, ref, watch } from "vue"

globalThis.window = {
	frappe: { boot: { site_name: "site.local" } },
	location: { origin: "http://site.local", protocol: "http:", hostname: "site.local", host: "site.local" },
	addEventListener() {},
	removeEventListener() {},
}
globalThis.document = { visibilityState: "visible", cookie: "", addEventListener() {}, removeEventListener() {} }

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const realtime = await import("../src/api/realtime.js")
const { useRowSelection } = await import("../src/components/common/childGrid/rowSelection.js")
const { LAYSHEET_JOB_RESULTS } = await import("../src/composables/useTrackedJob.js")
const { getConnectionIndicator } = await import("../src/components/navigation/connectionIndicator.js")
const { findLinkedNames, hasRelatedChange, useRelatedDocumentsRealtime } = await import("../src/composables/useRelatedDocumentsRealtime.js")

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

function fakeSocket() {
	const handlers = new Map()
	return {
		connected: false, active: false, sent: [],
		io: { on() {}, reconnectionAttempts() {}, reconnectionDelayMax() {} },
		on(event, handler) { handlers.set(event, [...(handlers.get(event) || []), handler]) },
		off(event, handler) { handlers.set(event, (handlers.get(event) || []).filter((item) => item !== handler)) },
		connect() { this.active = true },
		emit(...args) { this.sent.push(args) },
		serverEmit(event, ...args) { for (const handler of handlers.get(event) || []) handler(...args) },
		open() { this.connected = true; this.serverEmit("connect") },
	}
}

const DC = "YRP Delivery Challan"
const GRN = "YRP Goods Received Note"
const relations = [
	{ doctype: DC, filters: { work_order: "WO-1" } },
	{ doctype: GRN, filters: { against: "YRP Work Order", against_id: "WO-1" } },
]

test("connection indicator stays hidden until live use, then follows the socket and the browser", () => {
	assert.equal(getConnectionIndicator({ status: "offline", hasLiveUse: false }), null)
	assert.equal(getConnectionIndicator({ status: "connected", hasLiveUse: true }).tone, "connected")
	assert.equal(getConnectionIndicator({ status: "connected", hasLiveUse: true }).label, "", "connected is a bare dot")
	assert.equal(getConnectionIndicator({ status: "connecting", hasLiveUse: true }).label, "Reconnecting…")
	const offline = getConnectionIndicator({ status: "offline", hasLiveUse: true })
	assert.deepEqual([offline.tone, offline.label, offline.title], ["offline", "Offline — data may be out of date", "Offline — data may be out of date"])
	assert.equal(getConnectionIndicator({ status: "connected", hasLiveUse: true, isBrowserOnline: false }).tone, "offline")
})

test("a related change refreshes for shown names without a lookup and checks unknown names once per doctype", async () => {
	const lookups = []
	const findLinked = async (relation, names) => { lookups.push([relation.doctype, names]); return relation.doctype === GRN ? ["GRN-9"] : [] }
	assert.equal(await hasRelatedChange(relations, [{ doctype: DC, name: "DC-1" }], new Set(["DC-1"]), findLinked), true)
	assert.deepEqual(lookups, [])
	assert.equal(await hasRelatedChange(relations, [{ doctype: DC, name: "DC-7" }, { doctype: DC, name: "DC-7" }], new Set(), findLinked), false)
	assert.deepEqual(lookups, [[DC, ["DC-7"]]])
	assert.equal(await hasRelatedChange(relations, [{ doctype: GRN, name: "GRN-9" }], new Set(), findLinked), true)
})

test("findLinkedNames asks for only the changed names under the parent's filters", async () => {
	const urls = []
	globalThis.fetch = async (url) => { urls.push(decodeURIComponent(url).replaceAll("+", " ")); return { ok: true, status: 200, json: async () => ({ data: [{ name: "DC-7" }] }) } }
	assert.deepEqual(await findLinkedNames(relations[0], ["DC-7", "DC-8"]), ["DC-7"])
	assert.match(urls[0], /\/api\/resource\/YRP Delivery Challan\?/)
	assert.match(urls[0], /\[\["YRP Delivery Challan","work_order","=","WO-1"\],\["YRP Delivery Challan","name","in",\["DC-7","DC-8"\]\]\]/)
	assert.match(urls[0], /limit_page_length=2/)
})

test("useRelatedDocumentsRealtime subscribes to the related doctypes and refreshes only for this parent", async () => {
	const socket = fakeSocket()
	realtime.setSocketClientLoader(async () => ({ io: () => socket }))
	const watched = ref(relations)
	const refreshes = []
	const scope = effectScope()
	scope.run(() => useRelatedDocumentsRealtime(watched, {
		knownNames: () => ["DC-1"],
		onChange: () => refreshes.push("refresh"),
		findLinked: async (_relation, names) => names.filter((name) => name === "GRN-NEW"),
	}))
	await flush()
	socket.open()
	assert.deepEqual(socket.sent, [["doctype_subscribe", DC], ["doctype_subscribe", GRN]])
	socket.serverEmit("list_update", { doctype: DC, name: "DC-OTHER" })
	await new Promise((resolve) => setTimeout(resolve, 600))
	assert.deepEqual(refreshes, [], "another Work Order's DC does not refresh this page")
	socket.serverEmit("list_update", { doctype: GRN, name: "GRN-NEW" })
	await new Promise((resolve) => setTimeout(resolve, 600))
	assert.deepEqual(refreshes, ["refresh"], "a new GRN for this Work Order refreshes the cards")
	socket.serverEmit("list_update", { doctype: DC, name: "DC-1" })
	await new Promise((resolve) => setTimeout(resolve, 600))
	assert.equal(refreshes.length, 2, "a shown DC refreshes")
	scope.stop()
	await flush()
	assert.deepEqual(socket.sent.slice(-2), [["doctype_unsubscribe", DC], ["doctype_unsubscribe", GRN]])
})

test("Work Order and Purchase Order pages refresh related cards in the background after pop-up actions", () => {
	for (const page of ["../src/departments/FabricWorkOrder.vue", "../src/departments/FabricPurchaseOrder.vue"]) {
		const text = source(page)
		assert.match(text, /async function relatedChanged\((payload)?\) \{ await refreshWorkspace\(\)(; emit\("changed", payload\))? \}/)
		assert.match(text, /useRelatedDocumentsRealtime\(/)
		assert.match(text, /useRefetchOnReturn\(refreshWorkspace\)/)
		assert.doesNotMatch(text.match(/const refreshWorkspace = coalesceRefetch\([\s\S]*?\n\}\)/)[0], /acting\.value = |loading\.value = /, "the refresh never flips page busy state")
	}
	assert.match(source("../src/departments/FabricWorkOrder.vue"), /async function materialIssueChanged\(\) \{ materialIssueVisible\.value = false; await refreshWorkspace\(\) \}/)
})

test("pop-ups follow remote changes: silent reload when clean, notice when there is unsaved input", () => {
	const dialog = source("../src/components/documents/DocumentTransactionDialog.vue")
	assert.match(dialog, /if \(dirty\.value\) remoteChange\.value = change\n\t\telse load\(\{ background: true \}\)/)
	for (const workspace of ["DeliveryChallanWorkspace", "GoodsReceivedNoteWorkspace"]) {
		const text = source(`../src/departments/fabric-store/${workspace}.vue`)
		assert.match(text, /applyWorkspace\(nextWorkspace\)\n\t\tif \(refresh\) activeTab\.value = tab/, `${workspace} keeps the tab on refresh`)
		assert.match(text, /if \(!refresh\) clearWorkspaceState\(requestedName\)/, `${workspace} keeps data when a refresh fails`)
	}
})

test("the top bar shows the connection indicator next to the context, before the account menu", () => {
	const app = source("../src/App.vue")
	assert.ok(app.indexOf("<ConnectionIndicator />") > app.indexOf("app-topbar__context"))
	assert.ok(app.indexOf("<ConnectionIndicator />") < app.indexOf("<AccountMenu />"))
})

const DONE = "yrp_laysheet_job_done"

async function trackedJob({ timeoutMs = 1_000, pollMs = 1_000, getStatus = async () => ({ status: "queued" }) } = {}) {
	const { useTrackedJob } = await import("../src/composables/useTrackedJob.js")
	const socket = fakeSocket()
	realtime.setSocketClientLoader(async () => ({ io: () => socket }))
	const done = []
	const scope = effectScope()
	const job = scope.run(() => useTrackedJob({ onDone: (status) => done.push(status), timeoutMs, pollMs, getStatus }))
	return { socket, done, scope, job }
}

test("useTrackedJob ends only on its own job's event, never on a document save or another job", async () => {
	const { socket, done, scope, job } = await trackedJob()
	await job.run(async () => ({ job_token: "T1" }))
	await flush()
	socket.open()
	assert.equal(job.isRunning.value, true)
	socket.serverEmit("doc_update", { doctype: "SD YRP Cutting Plan", name: "CP-1", modified: "x" })
	socket.serverEmit("list_update", { doctype: "SD YRP Cutting Plan", name: "CP-1" })
	socket.serverEmit(DONE, { job_token: "OTHER", status: "finished" })
	assert.deepEqual(done, [], "someone else's save or job does not finish this one")
	socket.serverEmit(DONE, { job_token: "T1", status: "finished" })
	assert.deepEqual(done, ["finished"])
	assert.equal(job.isRunning.value, false)
	socket.serverEmit(DONE, { job_token: "T1", status: "failed" })
	assert.deepEqual(done, ["finished"], "a job reports once")
	scope.stop()
})

test("useTrackedJob keeps an event that beats the queuing response and reports failures", async () => {
	const { socket, done, scope, job } = await trackedJob()
	await flush()
	socket.open()
	await job.run(async () => {
		await flush()
		socket.serverEmit(DONE, { job_token: "FAST", status: "failed" })
		return { job_token: "FAST" }
	})
	assert.deepEqual(done, ["failed"])
	await assert.rejects(job.run(async () => { throw new Error("Not permitted") }), /Not permitted/)
	assert.equal(job.isRunning.value, false, "a refused request tracks nothing")
	scope.stop()
})

test("useTrackedJob falls back to the status poll, then to a timeout, and stops on disposal", async () => {
	const polled = []
	const statuses = ["queued", "finished"]
	const first = await trackedJob({ pollMs: 5, getStatus: async (token) => { polled.push(token); return { status: statuses.shift() } } })
	await first.job.run(async () => ({ job_token: "MISSED" }))
	await new Promise((resolve) => setTimeout(resolve, 40))
	assert.deepEqual(first.done, ["finished"], "a missed event is recovered by polling")
	assert.deepEqual(polled, ["MISSED", "MISSED"])
	first.scope.stop()

	const second = await trackedJob({ pollMs: 1_000, timeoutMs: 10 })
	await second.job.run(async () => ({ job_token: "SLOW" }))
	await new Promise((resolve) => setTimeout(resolve, 30))
	assert.deepEqual(second.done, ["timeout"])
	second.scope.stop()

	const third = await trackedJob({ pollMs: 5 })
	await third.job.run(async () => ({ job_token: "GONE" }))
	third.scope.stop()
	third.socket.serverEmit(DONE, { job_token: "GONE", status: "finished" })
	await new Promise((resolve) => setTimeout(resolve, 20))
	assert.deepEqual(third.done, [], "nothing is reported after the page is gone")
})

function cuttingPlanActions(trackedJobs) {
	const emitted = []
	const calls = []
	const script = readFileSync(new URL("../src/departments/cutting/CuttingPlanActions.vue", import.meta.url), "utf8").split("<script setup>")[1].split("</script>")[0].replace(/^import .*$/gm, "")
	const api = new Function("ref", "computed", "reactive", "defineProps", "defineEmits", "callMethod", "copyCompletedReportImage", "window", "watch", "onBeforeUnmount", "useRowSelection", "useTrackedJob", "LAYSHEET_JOB_RESULTS", `${script}\nreturn { runPlanAction, feedback, feedbackSeverity }`)(
		ref, computed, reactive, () => ({ doc: { name: "CP-1" }, data: {} }), () => (...args) => emitted.push(args),
		async (method) => { calls.push(method.split(".").pop()); return { job_token: "T" } }, () => {}, { setTimeout: () => 0, clearTimeout: () => {} }, watch, () => {},
		useRowSelection,
		(options) => { trackedJobs.push(options); return { isRunning: ref(false), run: (queue) => queue() } }, LAYSHEET_JOB_RESULTS,
	)
	return { ...api, emitted, calls }
}

test("Calculate LaySheets refreshes the plan only when its job finishes", async () => {
	const jobs = []
	const plan = cuttingPlanActions(jobs)
	await plan.runPlanAction("calculate")
	assert.deepEqual(plan.calls, ["calculate_laysheets"])
	assert.deepEqual(plan.emitted, [], "queuing does not refetch the old totals")
	jobs[0].onDone("failed")
	assert.deepEqual([plan.emitted, plan.feedbackSeverity.value], [[], "error"])
	jobs[0].onDone("timeout")
	assert.deepEqual([plan.emitted, plan.feedbackSeverity.value], [[], "warn"])
	jobs[0].onDone("finished")
	assert.deepEqual([plan.emitted, plan.feedback.value], [[["refresh"]], "LaySheets calculated."])
	await plan.runPlanAction("generate")
	assert.deepEqual(plan.emitted.at(-1), ["refresh"], "synchronous actions still refresh at once")
	const order = source("../src/departments/cutting/order/CuttingOrderActions.vue")
	assert.match(order, /await laysheetJob\.run\(\(\) => callMethod\([^\n]*calculate_laysheets[^\n]*\)\)\n\t\} catch/)
	assert.match(order, /if \(result\.refresh\) emit\("refresh"\)/)
})

test("related-document refreshes stop with the page: no refetch or state update after disposal", async () => {
	const socket = fakeSocket()
	realtime.setSocketClientLoader(async () => ({ io: () => socket }))
	let resolveLookup
	const refreshes = []
	const scope = effectScope()
	scope.run(() => useRelatedDocumentsRealtime(relations, {
		knownNames: () => [],
		onChange: () => refreshes.push("refresh"),
		findLinked: () => new Promise((resolve) => { resolveLookup = resolve }),
	}))
	await flush()
	socket.open()
	socket.serverEmit("list_update", { doctype: DC, name: "DC-NEW" })
	await new Promise((resolve) => setTimeout(resolve, 600))
	scope.stop()
	resolveLookup(["DC-NEW"])
	await flush()
	assert.deepEqual(refreshes, [], "a lookup that outlives the page does not refresh it")
	for (const page of ["../src/departments/FabricWorkOrder.vue", "../src/departments/FabricPurchaseOrder.vue"]) {
		const text = source(page)
		assert.match(text, /onScopeDispose\(\(\) => \{ isDisposed = true; refreshWorkspace\.cancel\(\) \}\)/)
		assert.match(text, /if \(!isDisposed && loadAtStart === loadSequence/)
	}
})

test("long action dialogs cannot be dismissed mid-request", () => {
	assert.match(source("../src/departments/cutting/bulk/BulkDeliveryDialog.vue"), /:dismissable-mask="!saving" :closable="!saving"/)
	assert.match(source("../src/departments/cutting/bulk/BulkPrintDialog.vue"), /:dismissable-mask="!printing" :closable="!printing"/)
	assert.match(source("../src/departments/cutting/CuttingLaySheetDialog.vue"), /<Dialog :visible="visible" modal :dismissable-mask="!busy"/)
})
