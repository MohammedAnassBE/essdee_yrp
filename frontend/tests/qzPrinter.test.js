import assert from "node:assert/strict"
import test from "node:test"

import { APPROVAL_TIMEOUT_MS, QZ_MESSAGES, getQzPrinters } from "../src/api/qzPrinter.js"

const flush = () => new Promise(setImmediate)
const UNREACHABLE = "Unable to establish connection with QZ"

function qzWindow(t, { protocol = "https:", hostname = "erp.example.com", connect, find = async () => ["Zebra"] } = {}) {
	const saved = globalThis.window
	const calls = { connect: 0, disconnect: 0, find: 0, sha256: null, promise: null, socketType: null, launched: [] }
	const qz = {
		api: {
			setPromiseType: (type) => { calls.promise = type },
			setSha256Type: (type) => { calls.sha256 = type },
			setWebSocketType: (type) => { calls.socketType = type },
		},
		websocket: {
			active: false,
			isActive: () => qz.websocket.active,
			connect: (options) => { calls.connect += 1; return connect(qz, options) },
			disconnect: async () => { calls.disconnect += 1; qz.websocket.active = false },
		},
		printers: { find: () => { calls.find += 1; return find() } },
		open() { qz.websocket.active = true },
	}
	globalThis.window = { qz, sha256: (data) => `hash:${data}`, location: { protocol, hostname, assign: (url) => calls.launched.push(url) } }
	t.after(() => { globalThis.window = saved })
	return { qz, calls }
}

test("QZ: wires promise and SHA-256 like Frappe's qz_init and keeps qz-tray's own WebSocket", async t => {
	const { calls } = qzWindow(t, { connect: async (qz) => qz.open() })
	assert.deepEqual(await getQzPrinters(), ["Zebra"])
	assert.equal(calls.sha256("abc"), "hash:abc")
	assert.ok(calls.promise((resolve) => resolve(1)) instanceof Promise)
	assert.equal(calls.socketType, null)
})

test("QZ: like Desk, an unreachable QZ Tray is launched and retried three times", async t => {
	const options = []
	const { calls } = qzWindow(t, { connect: async (qz, value) => { options.push(value); if (options.length === 1) throw new Error(UNREACHABLE); qz.open() } })
	assert.deepEqual(await getQzPrinters(), ["Zebra"])
	assert.deepEqual(options, [undefined, { retries: 3, delay: 1 }])
	assert.deepEqual(calls.launched, ["qz:launch"])
})

test("QZ: an unreachable QZ Tray on an https site gives the start-QZ-Tray hint with QZ's own error", async t => {
	const { calls } = qzWindow(t, { connect: async () => { throw new Error(UNREACHABLE) } })
	await assert.rejects(getQzPrinters(), { message: `${QZ_MESSAGES.unreachable} (QZ Tray: ${UNREACHABLE})` })
	assert.equal(calls.connect, 2)
})

test("QZ: an unreachable QZ Tray on an http site says Chrome blocks non-HTTPS sites", async t => {
	qzWindow(t, { protocol: "http:", connect: async () => { throw new Error(UNREACHABLE) } })
	await assert.rejects(getQzPrinters(), { message: `${QZ_MESSAGES.insecure} (QZ Tray: ${UNREACHABLE})` })
})

test("QZ: http on localhost is not treated as an insecure site", async t => {
	qzWindow(t, { protocol: "http:", hostname: "localhost", connect: async () => { throw new Error(UNREACHABLE) } })
	await assert.rejects(getQzPrinters(), { message: `${QZ_MESSAGES.unreachable} (QZ Tray: ${UNREACHABLE})` })
})

test("QZ: discovery waits for the QZ Allow prompt and then lists printers", async t => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	let approve
	qzWindow(t, { connect: (qz) => new Promise((resolve) => { approve = () => { qz.open(); resolve() } }) })
	const stages = []
	const result = getQzPrinters({ onStatus: (stage) => stages.push(stage) })
	await flush()
	t.mock.timers.tick(APPROVAL_TIMEOUT_MS - 1)
	await flush()
	approve()
	assert.deepEqual(await result, ["Zebra"])
	assert.deepEqual(stages, ["connecting", "approve-printers"])
})

test("QZ: an unanswered connection ends with a clear message instead of spinning forever", async t => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	const { calls } = qzWindow(t, { connect: () => new Promise(() => {}) })
	const result = getQzPrinters()
	result.catch(() => {})
	await flush()
	t.mock.timers.tick(APPROVAL_TIMEOUT_MS)
	await assert.rejects(result, { message: QZ_MESSAGES.connectApproval })
	assert.equal(calls.disconnect, 1)
})

test("QZ: concurrent discoveries share one connect attempt instead of reusing an unapproved socket", async t => {
	let approve
	const { calls } = qzWindow(t, { connect: (qz) => new Promise((resolve) => { approve = () => { qz.open(); resolve() } }) })
	const first = getQzPrinters()
	await flush()
	const second = getQzPrinters()
	await flush()
	assert.equal(calls.find, 0, "printers.find must wait until QZ Tray accepted the connection")
	approve()
	assert.deepEqual(await Promise.all([first, second]), [["Zebra"], ["Zebra"]])
	assert.equal(calls.connect, 1)
})

test("QZ: a blocked or denied request reports QZ Tray's reason", async t => {
	qzWindow(t, { connect: async () => { throw new Error("Connection blocked by client") } })
	await assert.rejects(getQzPrinters(), { message: "QZ Tray: Connection blocked by client" })
})
