#!/usr/bin/env node

import assert from "node:assert/strict"

import { callMethod } from "../frontend/src/api/frappe.js"
import {
	createCancellableDelay,
	createStatusRequestQueue,
	envelopeState,
	isDefinitiveReportError,
	isReportTrackingState,
	isTerminalReportState,
	pollingDelay,
	reportErrorMessage,
	resumeStorageKey,
	shouldRemoveStoredTracking,
} from "../frontend/src/composables/webReportState.js"

assert.equal(envelopeState({ mode: "sync", result: [] }), "ready")
assert.equal(envelopeState({ mode: "background", job: { status: "Queued" } }), "queued")
assert.equal(envelopeState({ mode: "background", job: { status: "Started" } }), "running")
assert.equal(envelopeState({ mode: "background", job: { status: "Completed" } }), "ready")
assert.equal(envelopeState({ mode: "background", job: { status: "Error" } }), "error")
assert.equal(envelopeState({ expired: true, job: { status: "Completed" } }), "expired")

assert.equal(reportErrorMessage(new TypeError("Failed to fetch")), "The report server did not respond. Narrow the filters or try again.")
assert.equal(reportErrorMessage(new Error("Too many stock ledger entries (500000+). Please narrow your filters.")), "Too many stock ledger entries (500000+). Please narrow your filters.")
assert.equal(reportErrorMessage(undefined), "Unable to generate this report.")

assert.equal(pollingDelay(0), 2_000)
assert.equal(pollingDelay(9_999), 2_000)
assert.equal(pollingDelay(10_000), 5_000)
assert.equal(pollingDelay(59_999), 5_000)
assert.equal(pollingDelay(60_000), 10_000)
assert.equal(isTerminalReportState("ready"), true)
assert.equal(isTerminalReportState("running"), false)
assert.equal(isReportTrackingState("queued"), true)
assert.equal(isReportTrackingState("running"), true)
assert.equal(isReportTrackingState("ready"), false)
assert.equal(shouldRemoveStoredTracking("queued", false), true)
assert.equal(shouldRemoveStoredTracking("queued", true), false)
assert.equal(shouldRemoveStoredTracking("ready", true), true)
assert.equal(resumeStorageKey("stock-balance"), "yrp:web-report:stock-balance")

const retryDelay = createCancellableDelay()
const cancelledDelay = retryDelay.wait(50)
retryDelay.cancel()
assert.equal(await cancelledDelay, false)
assert.equal(await retryDelay.wait(0), true)

const firstStatus = deferred()
const secondStatus = deferred()
const appliedStatuses = []
let statusRequests = 0
const statusQueue = createStatusRequestQueue()
const firstPoll = statusQueue.run(
	() => { statusRequests += 1; return firstStatus.promise },
	(envelope) => { appliedStatuses.push(envelope.state); return envelope.state === "ready" },
)
const secondPoll = statusQueue.run(
	() => { statusRequests += 1; return secondStatus.promise },
	(envelope) => { appliedStatuses.push(envelope.state); return envelope.state === "ready" },
)
const staleQueuedPoll = statusQueue.run(
	async () => { statusRequests += 1; return { state: "running" } },
	(envelope) => { appliedStatuses.push(envelope.state); return false },
)
await nextTask()
assert.equal(statusRequests, 1)
firstStatus.resolve({ state: "running" })
await firstPoll
await nextTask()
assert.equal(statusRequests, 2)
secondStatus.resolve({ state: "ready" })
assert.deepEqual(await secondPoll, { ignored: false, terminal: true })
assert.deepEqual(await staleQueuedPoll, { ignored: true, terminal: false })
assert.equal(statusRequests, 2)
assert.deepEqual(appliedStatuses, ["running", "ready"])

const invalidatedStatus = deferred()
const invalidatedQueue = createStatusRequestQueue()
let staleApplied = false
const stalePoll = invalidatedQueue.run(
	() => invalidatedStatus.promise,
	() => { staleApplied = true; return false },
)
await nextTask()
invalidatedQueue.invalidate()
let freshRequests = 0
const freshPoll = invalidatedQueue.run(
	async () => { freshRequests += 1; return { state: "running" } },
	() => false,
)
await nextTask()
assert.equal(freshRequests, 1)
assert.deepEqual(await freshPoll, { ignored: false, terminal: false })
invalidatedStatus.resolve({ state: "running" })
assert.deepEqual(await stalePoll, { ignored: true, terminal: false })
assert.equal(staleApplied, false)

const retryQueue = createStatusRequestQueue()
let retryAttempts = 0
await assert.rejects(
	retryQueue.run(async () => { retryAttempts += 1; throw new TypeError("Failed to fetch") }, () => false),
	/Failed to fetch/,
)
assert.deepEqual(await retryQueue.run(
	async () => { retryAttempts += 1; return { state: "running" } },
	() => false,
), { ignored: false, terminal: false })
assert.equal(retryAttempts, 2)
assert.equal(isDefinitiveReportError(new TypeError("Failed to fetch")), false)
assert.equal(isDefinitiveReportError({ status: 503 }), false)
assert.equal(isDefinitiveReportError({ status: 403 }), true)
assert.equal(isDefinitiveReportError({ status: 417 }), true)

const savedFetch = globalThis.fetch
const savedWindow = globalThis.window
globalThis.window = {
	csrf_token: "token",
	frappe: {},
	location: { assign() {}, pathname: "/web/reports" },
}
globalThis.fetch = async () => ({
	status: 403,
	ok: false,
	json: async () => ({ message: "Not permitted" }),
})
await assert.rejects(
	callMethod("yrp.api.web_reports.get_report_job"),
	(reason) => reason.status === 403,
)
globalThis.fetch = savedFetch
globalThis.window = savedWindow

function deferred() {
	let resolve
	let reject
	const promise = new Promise((resolvePromise, rejectPromise) => {
		resolve = resolvePromise
		reject = rejectPromise
	})
	return { promise, resolve, reject }
}

function nextTask() {
	return new Promise((resolve) => setImmediate(resolve))
}

console.log("web report state OK")
