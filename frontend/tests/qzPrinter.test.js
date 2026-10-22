import assert from "node:assert/strict"
import test from "node:test"

import { getQzPrinters } from "../src/api/qzPrinter.js"

function qzWindow(t, { connect, find = async () => ["Zebra"] }) {
	const previous = globalThis.window
	const qz = { api: { setPromiseType() {}, setSha256Type() {} }, websocket: { isActive: () => false, connect }, printers: { find } }
	globalThis.window = { qz, sha256() {} }
	t.after(() => { globalThis.window = previous })
	return qz
}

test("QZ: discovery waits for the QZ Tray site-approval prompts like MRP Desk", async t => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	let approveConnect, approvePrinters
	qzWindow(t, {
		connect: () => new Promise(resolve => { approveConnect = resolve }),
		find: () => new Promise(resolve => { approvePrinters = resolve }),
	})
	let settled = false
	const result = getQzPrinters().finally(() => { settled = true })
	await new Promise(setImmediate)
	t.mock.timers.tick(60000)
	await new Promise(setImmediate)
	assert.equal(settled, false, "a pending QZ approval prompt must not be reported as a connection failure")
	approveConnect()
	await new Promise(setImmediate)
	t.mock.timers.tick(60000)
	approvePrinters(["Zebra"])
	assert.deepEqual(await result, ["Zebra"])
})

test("QZ: a blocked or denied request reports QZ Tray's reason, not 'could not connect'", async t => {
	qzWindow(t, { connect: async () => { throw new Error("Connection blocked by client") } })
	await assert.rejects(getQzPrinters(), error => {
		assert.match(error.message, /Connection blocked by client/)
		assert.doesNotMatch(error.message, /Could not connect/)
		return true
	})
})

test("QZ: an unreachable QZ Tray still gives the start-QZ-Tray hint", async t => {
	qzWindow(t, { connect: async () => { throw new Error("Unable to establish connection with QZ") } })
	await assert.rejects(getQzPrinters(), /Could not connect to QZ Tray\. Start QZ Tray on this computer and try again\./)
})
