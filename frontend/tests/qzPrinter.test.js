import assert from "node:assert/strict"
import test from "node:test"

import { APPROVAL_TIMEOUT_MS, QZ_MESSAGES, REACH_TIMEOUT_MS, getQzPrinters } from "../src/api/qzPrinter.js"

const flush = () => new Promise(setImmediate)

class FakeSocket extends EventTarget {}

function qzWindow(t, { permission = "granted", connect, find = async () => ["Zebra"] } = {}) {
	const saved = { window: globalThis.window, WebSocket: globalThis.WebSocket, navigator: Object.getOwnPropertyDescriptor(globalThis, "navigator") }
	const calls = { connect: 0, disconnect: 0, find: 0, sha256: null, promise: null, launched: [] }
	const qz = {
		api: {
			setPromiseType: (type) => { calls.promise = type },
			setSha256Type: (type) => { calls.sha256 = type },
			setWebSocketType: (type) => { qz.Socket = type },
		},
		websocket: {
			active: false,
			isActive: () => qz.websocket.active,
			connect: () => { calls.connect += 1; return connect(qz) },
			disconnect: async () => { calls.disconnect += 1; qz.websocket.active = false },
		},
		printers: { find: () => { calls.find += 1; return find() } },
		open() {
			qz.websocket.active = true
			new qz.Socket("wss://localhost:8181").dispatchEvent(new Event("open"))
		},
	}
	globalThis.WebSocket = FakeSocket
	globalThis.window = { qz, sha256: (data) => `hash:${data}`, location: { assign: (url) => calls.launched.push(url) } }
	Object.defineProperty(globalThis, "navigator", { configurable: true, value: { permissions: { query: async () => ({ state: permission }) } } })
	t.after(() => {
		globalThis.window = saved.window
		globalThis.WebSocket = saved.WebSocket
		Object.defineProperty(globalThis, "navigator", saved.navigator)
	})
	return { qz, calls }
}

test("QZ: wires promise, SHA-256 and a tracked WebSocket type before connecting, like Frappe's qz_init", async t => {
	const { qz, calls } = qzWindow(t, { connect: async (qz) => qz.open() })
	assert.deepEqual(await getQzPrinters(), ["Zebra"])
	assert.equal(calls.sha256("abc"), "hash:abc")
	assert.ok(calls.promise((resolve) => resolve(1)) instanceof Promise)
	assert.ok(new qz.Socket("wss://localhost:8181") instanceof FakeSocket)
})

test("QZ: a denied local network permission does not stop the connect attempt", async t => {
	const { calls } = qzWindow(t, { permission: "denied", connect: async (qz) => qz.open() })
	assert.deepEqual(await getQzPrinters(), ["Zebra"])
	assert.equal(calls.connect, 1)
})

test("QZ: an unreachable QZ Tray with a denied local network permission gets the site-settings fix", async t => {
	const { calls } = qzWindow(t, { permission: "denied", connect: async () => { throw new Error("Unable to establish connection with QZ") } })
	await assert.rejects(getQzPrinters(), { message: QZ_MESSAGES.blocked })
	assert.equal(calls.connect, 2)
})

test("QZ: like Desk, an unreachable QZ Tray is launched and retried three times", async t => {
	let attempts = 0
	const options = []
	const { qz, calls } = qzWindow(t, { connect: async (qz) => { if (++attempts === 1) throw new Error("Unable to establish connection with QZ"); qz.open() } })
	const connect = qz.websocket.connect
	qz.websocket.connect = (value) => { options.push(value); return connect(value) }
	assert.deepEqual(await getQzPrinters(), ["Zebra"])
	assert.deepEqual(options, [undefined, { retries: 3, delay: 1 }])
	assert.deepEqual(calls.launched, ["qz:launch"])
})

test("QZ: a socket the browser never opens (pending permission prompt) times out with a browser hint", async t => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	const { calls } = qzWindow(t, { permission: "prompt", connect: () => new Promise(() => {}) })
	const stages = []
	const result = getQzPrinters({ onStatus: (stage) => stages.push(stage) })
	result.catch(() => {})
	await flush()
	t.mock.timers.tick(REACH_TIMEOUT_MS)
	await assert.rejects(result, { message: QZ_MESSAGES.unreached })
	assert.deepEqual(stages, ["browser-permission"])
	assert.equal(calls.disconnect, 1)
})

test("QZ: once QZ Tray is reached, discovery waits for the Allow prompt and then lists printers", async t => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	let approve
	qzWindow(t, { connect: (qz) => new Promise((resolve) => { qz.open(); approve = resolve }) })
	const stages = []
	const result = getQzPrinters({ onStatus: (stage) => stages.push(stage) })
	await flush()
	t.mock.timers.tick(REACH_TIMEOUT_MS + 30000)
	await flush()
	approve()
	assert.deepEqual(await result, ["Zebra"])
	assert.deepEqual(stages, ["connecting", "approve-connection", "approve-printers"])
})

test("QZ: an unanswered QZ Allow prompt ends with a clear message instead of spinning forever", async t => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	const { calls } = qzWindow(t, { connect: (qz) => new Promise(() => qz.open()) })
	const result = getQzPrinters()
	result.catch(() => {})
	await flush()
	t.mock.timers.tick(APPROVAL_TIMEOUT_MS)
	await assert.rejects(result, { message: QZ_MESSAGES.connectApproval })
	assert.equal(calls.disconnect, 1)
})

test("QZ: concurrent discoveries share one connect attempt instead of reusing an unapproved socket", async t => {
	let approve
	const { calls } = qzWindow(t, { connect: (qz) => new Promise((resolve) => { qz.open(); approve = resolve }) })
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

test("QZ: an unreachable QZ Tray gives the start-QZ-Tray hint", async t => {
	qzWindow(t, { connect: async () => { throw new Error("Unable to establish connection with QZ") } })
	await assert.rejects(getQzPrinters(), { message: QZ_MESSAGES.unreachable })
})
