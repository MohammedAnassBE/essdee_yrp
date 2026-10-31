import assert from "node:assert/strict"
import test from "node:test"
import { effectScope, nextTick, ref } from "vue"

globalThis.window = {
	frappe: { boot: { site_name: "site.local" } },
	location: { origin: "http://site.local", protocol: "http:", hostname: "site.local" },
}
const visibility = fakeDocument()
globalThis.document = visibility

const realtime = await import("../src/api/realtime.js")
const { useDocRealtime } = await import("../src/composables/live/useDocRealtime.js")
const { useListRealtime } = await import("../src/composables/live/useListRealtime.js")
const { useRefetchOnReturn } = await import("../src/composables/live/useRefetchOnReturn.js")

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

function fakeDocument() {
	const listeners = new Set()
	return {
		visibilityState: "visible",
		addEventListener: (event, handler) => event === "visibilitychange" && listeners.add(handler),
		removeEventListener: (event, handler) => listeners.delete(handler),
		setVisible(visible) {
			this.visibilityState = visible ? "visible" : "hidden"
			for (const handler of [...listeners]) handler()
		},
	}
}

/** `manualAcks` models the Python server, which acknowledges a subscribe only after its async permission check. */
function fakeSocket({ manualAcks = false } = {}) {
	const handlers = new Map()
	const managerHandlers = new Map()
	const socket = {
		connected: false, active: false, connects: 0, sent: [], acks: [], attempts: 5, delayMax: 5000,
		io: {
			on(event, handler) { managerHandlers.set(event, handler) },
			reconnectionAttempts(value) { this.owner.attempts = value },
			reconnectionDelayMax(value) { this.owner.delayMax = value },
			fire(event) { managerHandlers.get(event)?.() },
		},
		on(event, handler) { handlers.set(event, [...(handlers.get(event) || []), handler]) },
		off(event, handler) { handlers.set(event, (handlers.get(event) || []).filter((item) => item !== handler)) },
		connect() { this.connects += 1; this.active = true },
		emit(...args) { this.sent.push(args) },
		serverEmit(event, ...args) { for (const handler of handlers.get(event) || []) handler(...args) },
		open() { this.connected = true; this.serverEmit("connect") },
		drop(reason = "transport close") { this.connected = false; this.serverEmit("disconnect", reason) },
		ack() { this.acks.shift()() },
	}
	if (manualAcks) socket.timeout = () => ({ emit: (...args) => { socket.acks.push(args.pop()); socket.sent.push(args) } })
	return socket
}

async function useSocket(options) {
	const socket = fakeSocket(options)
	socket.io.owner = socket
	realtime.setSocketClientLoader(async () => ({ io: () => socket }))
	return socket
}

test("rooms are reference counted, joined on connect and re-joined after a reconnect", async () => {
	const socket = await useSocket()
	const reconnects = []
	const offReconnect = realtime.onReconnect(() => reconnects.push(socket.sent.length))
	const releaseA = realtime.subscribeDoctype("ToDo")
	const releaseB = realtime.subscribeDoctype("ToDo")
	const releaseDoc = realtime.subscribeDoc("ToDo", "T-1")
	await flush()
	assert.deepEqual([socket.connects > 0, socket.attempts, socket.delayMax, realtime.realtimeStatus.value], [true, Infinity, 15000, "connecting"])
	assert.deepEqual(socket.sent, [])
	socket.open()
	assert.equal(realtime.realtimeStatus.value, "connected")
	assert.deepEqual(socket.sent, [["doctype_subscribe", "ToDo"], ["doc_subscribe", "ToDo", "T-1"]])
	assert.deepEqual(reconnects, [], "the first connect is not a reconnect")
	socket.active = true
	socket.drop()
	assert.equal(realtime.realtimeStatus.value, "connecting")
	socket.open()
	assert.equal(socket.sent.length, 4, "both rooms are re-joined")
	assert.deepEqual(reconnects, [4])
	releaseA()
	releaseA()
	await flush()
	assert.equal(socket.sent.length, 4, "a second holder keeps the room")
	releaseB()
	releaseDoc()
	await flush()
	assert.deepEqual(socket.sent.slice(4), [["doctype_unsubscribe", "ToDo"], ["doc_unsubscribe", "ToDo", "T-1"]])
	socket.io.fire("reconnect_failed")
	assert.equal(realtime.realtimeStatus.value, "offline")
	offReconnect()
})

test("a server-side disconnect reconnects while live rooms are held", async (t) => {
	t.mock.timers.enable({ apis: ["setTimeout"] })
	const socket = await useSocket()
	const release = realtime.subscribeDoctype("ToDo")
	await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
	socket.open()
	const connects = socket.connects
	socket.active = false
	socket.drop("io server disconnect")
	assert.equal(realtime.realtimeStatus.value, "offline")
	t.mock.timers.tick(2000)
	assert.equal(socket.connects, connects + 1)
	release()
})

test("useDocRealtime reports other sessions' saves and ignores this page's own save", async () => {
	const socket = await useSocket()
	const name = ref("T-1")
	const modified = ref("2026-10-31 10:00:00.000001")
	const saving = ref(false)
	const changes = []
	const scope = effectScope()
	scope.run(() => useDocRealtime("ToDo", name, { localModified: modified, isBusy: saving, onRemoteChange: (payload) => changes.push(payload.modified) }))
	await flush()
	socket.open()
	assert.deepEqual(socket.sent, [["doc_subscribe", "ToDo", "T-1"]])
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: modified.value })
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-2", modified: "x" })
	assert.deepEqual(changes, [], "own echo and other documents are ignored")
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "2026-10-31 10:05:00" })
	assert.deepEqual(changes, ["2026-10-31 10:05:00"])

	saving.value = true
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "2026-10-31 10:06:00" })
	modified.value = "2026-10-31 10:06:00"
	saving.value = false
	await nextTick()
	assert.equal(changes.length, 1, "an event that raced its own save response is an echo")

	visibility.setVisible(false)
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-1", modified: "2026-10-31 10:07:00" })
	assert.equal(changes.length, 1, "held while hidden")
	visibility.setVisible(true)
	assert.deepEqual(changes.at(-1), "2026-10-31 10:07:00")

	name.value = "T-2"
	await nextTick()
	await flush()
	assert.deepEqual(socket.sent.slice(1), [["doc_unsubscribe", "ToDo", "T-1"], ["doc_subscribe", "ToDo", "T-2"]])
	scope.stop()
	await flush()
	assert.deepEqual(socket.sent.at(-1), ["doc_unsubscribe", "ToDo", "T-2"])
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-2", modified: "y" })
	assert.equal(changes.length, 2)
})

test("useListRealtime debounces names across doctypes and caps a burst at maxWaitMs", async (t) => {
	const socket = await useSocket()
	const doctypes = ref(["ToDo", "Note"])
	const batches = []
	const scope = effectScope()
	await flush()
	t.mock.timers.enable({ apis: ["setTimeout", "Date"] })
	scope.run(() => useListRealtime(doctypes, (change) => batches.push(change), { debounceMs: 100, maxWaitMs: 250 }))
	await Promise.resolve(); await Promise.resolve(); await Promise.resolve()
	socket.open()
	assert.deepEqual(socket.sent, [["doctype_subscribe", "ToDo"], ["doctype_subscribe", "Note"]])
	socket.serverEmit("list_update", { doctype: "ToDo", name: "A", user: "a@x" })
	t.mock.timers.tick(60)
	socket.serverEmit("list_update", { doctype: "Note", name: "B", user: "b@x" })
	socket.serverEmit("list_update", { doctype: "ToDo", name: "A", user: "a@x" })
	socket.serverEmit("list_update", { doctype: "User", name: "C" })
	t.mock.timers.tick(99)
	assert.equal(batches.length, 0)
	t.mock.timers.tick(1)
	assert.deepEqual(batches.map(({ names, doctypes: changed, hasUnnamed }) => ({ names, changed, hasUnnamed })), [{ names: ["A", "B"], changed: ["ToDo", "Note"], hasUnnamed: false }])

	for (let elapsed = 0; elapsed < 300; elapsed += 50) {
		socket.serverEmit("list_update", { doctype: "ToDo", name: `N${elapsed}` })
		t.mock.timers.tick(50)
	}
	assert.equal(batches.length, 2, "a continuous burst still flushes by maxWaitMs")

	socket.serverEmit("list_update", { doctype: "ToDo" })
	t.mock.timers.tick(100)
	assert.equal(batches.at(-1).hasUnnamed, true)

	doctypes.value = ["Note"]
	await nextTick()
	t.mock.timers.reset()
	await flush()
	assert.deepEqual(socket.sent.at(-1), ["doctype_unsubscribe", "ToDo"])
	scope.stop()
	await flush()
	assert.deepEqual(socket.sent.at(-1), ["doctype_unsubscribe", "Note"])
})

test("useListRealtime holds events while the tab is hidden and flushes on return", async (t) => {
	const socket = await useSocket()
	const batches = []
	const scope = effectScope()
	scope.run(() => useListRealtime("ToDo", (change) => batches.push(change.names), { debounceMs: 10 }))
	await flush()
	socket.open()
	visibility.setVisible(false)
	socket.serverEmit("list_update", { doctype: "ToDo", name: "A" })
	await new Promise((resolve) => setTimeout(resolve, 20))
	assert.equal(batches.length, 0)
	visibility.setVisible(true)
	assert.deepEqual(batches, [["A"]])
	scope.stop()
})

test("useRefetchOnReturn refetches after a long absence and after a reconnect, never overlapping", async (t) => {
	const socket = await useSocket()
	await realtime.getSocket()
	t.mock.timers.enable({ apis: ["Date"] })
	let calls = 0
	let finish
	const scope = effectScope()
	scope.run(() => useRefetchOnReturn(() => { calls += 1; return new Promise((resolve) => { finish = resolve }) }, { minAwayMs: 1000 }))
	visibility.setVisible(false)
	t.mock.timers.tick(500)
	visibility.setVisible(true)
	assert.equal(calls, 0, "a short absence does not refetch")
	visibility.setVisible(false)
	t.mock.timers.tick(1000)
	visibility.setVisible(true)
	assert.equal(calls, 1)
	socket.open()
	socket.drop()
	socket.open()
	socket.open()
	assert.equal(calls, 1, "reconnects during a run queue a single rerun")
	finish()
	await flush()
	assert.equal(calls, 2)
	finish()
	await flush()
	visibility.setVisible(false)
	socket.open()
	assert.equal(calls, 2, "a reconnect while hidden waits for the return")
	visibility.setVisible(true)
	assert.equal(calls, 3)
	finish()
	scope.stop()
})

test("a release during a pending subscribe leaves the room only after the join is acknowledged", async () => {
	const socket = await useSocket({ manualAcks: true })
	const release = realtime.subscribeDoctype("Note")
	await flush()
	socket.open()
	assert.deepEqual(socket.sent, [["doctype_subscribe", "Note"]])
	assert.equal(realtime.hasLiveRooms.value, true)
	release()
	assert.equal(realtime.hasLiveRooms.value, false)
	assert.equal(socket.sent.length, 1, "no unsubscribe can overtake the pending join")
	socket.ack()
	assert.deepEqual(socket.sent.at(-1), ["doctype_unsubscribe", "Note"])
	const again = realtime.subscribeDoctype("Note")
	await flush()
	assert.equal(socket.sent.length, 2, "re-holding waits for the pending leave")
	socket.ack()
	assert.deepEqual(socket.sent.at(-1), ["doctype_subscribe", "Note"])
	socket.ack()
	again()
	socket.ack()
	assert.deepEqual(socket.sent.at(-1), ["doctype_unsubscribe", "Note"])
	assert.equal(socket.acks.length, 0)
})

test("reconnect handlers run only after every held room is joined again", async () => {
	const socket = await useSocket({ manualAcks: true })
	let reconnects = 0
	const off = realtime.onReconnect(() => { reconnects += 1 })
	const releaseList = realtime.subscribeDoctype("Note")
	const releaseDoc = realtime.subscribeDoc("Note", "N-1")
	await flush()
	socket.open()
	socket.ack()
	socket.ack()
	socket.drop()
	socket.open()
	assert.equal(socket.acks.length, 2)
	socket.drop()
	socket.open()
	socket.acks.splice(0, 2).forEach((ack) => ack())
	assert.equal(reconnects, 0, "acks from an older connection are ignored")
	socket.ack()
	assert.equal(reconnects, 0, "one room is still joining")
	socket.ack()
	assert.equal(reconnects, 1)
	off()
	releaseList()
	releaseDoc()
	socket.ack()
	socket.ack()
})

test("useDocRealtime.stop() while an event is held drops it, even with the scope still alive", async () => {
	const socket = await useSocket()
	const changes = []
	const scope = effectScope()
	const live = scope.run(() => useDocRealtime("ToDo", "T-9", { localModified: "a", onRemoteChange: (payload) => changes.push(payload) }))
	await flush()
	socket.open()
	visibility.setVisible(false)
	socket.serverEmit("doc_update", { doctype: "ToDo", name: "T-9", modified: "b" })
	live.stop()
	live.stop()
	visibility.setVisible(true)
	assert.deepEqual(changes, [])
	scope.stop()
})

test("useListRealtime.stop() while events are held drops them", async () => {
	const socket = await useSocket()
	const batches = []
	const scope = effectScope()
	const live = scope.run(() => useListRealtime("ToDo", (change) => batches.push(change), { debounceMs: 0 }))
	await flush()
	socket.open()
	visibility.setVisible(false)
	socket.serverEmit("list_update", { doctype: "ToDo", name: "A" })
	live.stop()
	visibility.setVisible(true)
	await flush()
	assert.deepEqual(batches, [])
	scope.stop()
})

test("useRefetchOnReturn.stop() ends returns and reconnects; a queued rerun dies with the scope", async (t) => {
	const socket = await useSocket()
	await realtime.getSocket()
	t.mock.timers.enable({ apis: ["Date"] })
	let calls = 0
	let finish
	const scope = effectScope()
	const live = scope.run(() => useRefetchOnReturn(() => { calls += 1; return new Promise((resolve) => { finish = resolve }) }, { minAwayMs: 0 }))
	visibility.setVisible(false)
	visibility.setVisible(true)
	assert.equal(calls, 1)
	socket.open()
	socket.open()
	scope.stop()
	finish()
	await flush()
	assert.equal(calls, 1, "the queued rerun is cancelled on dispose")
	visibility.setVisible(false)
	visibility.setVisible(true)
	socket.open()
	assert.equal(calls, 1)
	live.stop()
})

test("useRefetchOnReturn defers a queued rerun that comes due while hidden", async (t) => {
	const socket = await useSocket()
	await realtime.getSocket()
	t.mock.timers.enable({ apis: ["Date"] })
	let calls = 0
	let finish
	const scope = effectScope()
	scope.run(() => useRefetchOnReturn(() => { calls += 1; return new Promise((resolve) => { finish = resolve }) }, { minAwayMs: 1000 }))
	socket.open()
	socket.open()
	socket.open()
	assert.equal(calls, 1)
	visibility.setVisible(false)
	finish()
	await flush()
	assert.equal(calls, 1, "the rerun waits while hidden")
	visibility.setVisible(true)
	assert.equal(calls, 2, "and runs on return even after a short absence")
	finish()
	scope.stop()
})
