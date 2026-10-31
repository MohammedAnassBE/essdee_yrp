import { computed, readonly, ref } from "vue"

const LIVE_RECONNECT_DELAY_MAX_MS = 15_000
const SERVER_DISCONNECT_RETRY_MS = 2_000
// Frappe's Python realtime server acknowledges a subscribe once its permission check and join finish;
// the Node server never does, so its ack times out and the room is then assumed joined.
const ROOM_ACK_TIMEOUT_MS = 10_000

let socketPromise = null
let loadClient = () => import("socket.io-client")
let listenerCount = 0
let hasConnected = false
let currentSocket = null
let connectionGeneration = 0
let pendingReconnect = null
const rooms = new Map()
const reconnectHandlers = new Set()
const status = ref("offline")
const liveRoomCount = ref(0)

/** Shared socket state: "connected" | "connecting" | "offline". */
export const realtimeStatus = readonly(status)

/** True while any doc or doctype room is held, i.e. the page shows live data. */
export const hasLiveRooms = computed(() => liveRoomCount.value > 0)

/** Resolves the shared socket; socket.io-client loads on first use, so pages without live features skip it. */
export function getSocket() {
	if (socketPromise) return socketPromise
	socketPromise = loadClient().then(({ io }) => {
		const boot = window.frappe?.boot || {}
		const origin = boot.dev_server
			? `${window.location.protocol}//${window.location.hostname}:${boot.socketio_port}`
			: window.location.origin
		const socket = io(`${origin}/${boot.site_name}`, {
			autoConnect: false,
			withCredentials: true,
			reconnectionAttempts: 5,
		})
		trackConnection(socket)
		return socket
	})
	socketPromise.catch(() => { socketPromise = null })
	return socketPromise
}

/** Test seam: replaces the socket.io-client loader and drops the cached socket. */
export function setSocketClientLoader(loader) {
	loadClient = loader
	socketPromise = null
	currentSocket = null
	hasConnected = false
	pendingReconnect = null
	connectionGeneration += 1
	resetRooms()
	status.value = "offline"
}

function trackConnection(socket) {
	currentSocket = socket
	socket.on("connect", () => {
		status.value = "connected"
		connectionGeneration += 1
		if (hasConnected) pendingReconnect = connectionGeneration
		hasConnected = true
		for (const key of [...rooms.keys()]) syncRoom(key)
		runReconnectHandlersWhenJoined()
	})
	socket.on("disconnect", (reason) => {
		connectionGeneration += 1
		pendingReconnect = null
		resetRooms()
		status.value = socket.active ? "connecting" : "offline"
		// The server drops sockets when it restarts; socket.io never retries that on its own.
		if (reason === "io server disconnect" && liveRoomCount.value) setTimeout(() => connectLive(socket), SERVER_DISCONNECT_RETRY_MS)
	})
	socket.on("connect_error", () => { status.value = socket.active ? "connecting" : "offline" })
	socket.io?.on?.("reconnect_attempt", () => { status.value = "connecting" })
	socket.io?.on?.("reconnect_failed", () => { status.value = "offline" })
}

/** Live rooms retry forever with backoff, unlike one-off job listeners. */
function connectLive(socket) {
	socket.io?.reconnectionAttempts?.(Infinity)
	socket.io?.reconnectionDelayMax?.(LIVE_RECONNECT_DELAY_MAX_MS)
	if (socket.connected || !liveRoomCount.value) return
	status.value = "connecting"
	socket.connect()
}

/** Listens for a socket event and connects the socket; returns the unsubscribe function. */
export function onRealtime(event, handler) {
	let subscribed = true
	let connection = null
	listenerCount += 1
	getSocket().then((socket) => {
		if (!subscribed) return
		connection = socket
		socket.on(event, handler)
		if (!socket.connected && !socket.active) {
			status.value = "connecting"
			socket.connect()
		}
	}, () => {})
	return () => {
		if (!subscribed) return
		subscribed = false
		connection?.off(event, handler)
		listenerCount = Math.max(0, listenerCount - 1)
	}
}

export function hasRealtimeListeners() {
	return listenerCount > 0
}

/**
 * Calls `handler()` on every connect after the first, when room events may have been missed.
 * It runs once every held room is joined again (acknowledged), so a refetch it triggers cannot miss
 * a change committed before the join. Does not connect.
 */
export function onReconnect(handler) {
	reconnectHandlers.add(handler)
	return () => reconnectHandlers.delete(handler)
}

/** Joins the `doc:<doctype>/<name>` room (doc_update, docinfo_update); returns the release function. */
export function subscribeDoc(doctype, name) {
	return holdRoom(`doc:${doctype}/${name}`, ["doc_subscribe", doctype, name], ["doc_unsubscribe", doctype, name])
}

/** Joins the `doctype:<doctype>` room (list_update); returns the release function. */
export function subscribeDoctype(doctype) {
	return holdRoom(`doctype:${doctype}`, ["doctype_subscribe", doctype], ["doctype_unsubscribe", doctype])
}

/** Reference-counted room membership, re-joined on every connect because the server forgets rooms on disconnect. */
function holdRoom(key, subscribe, unsubscribe) {
	let room = rooms.get(key)
	if (!room) {
		room = { count: 0, subscribe, unsubscribe, joined: false, busy: false }
		rooms.set(key, room)
	}
	room.count += 1
	countLiveRooms()
	withSocket((socket) => {
		connectLive(socket)
		syncRoom(key)
	})
	let held = true
	return () => {
		if (!held) return
		held = false
		room.count -= 1
		countLiveRooms()
		syncRoom(key)
		runReconnectHandlersWhenJoined()
	}
}

/**
 * Moves one room's server membership towards its holders, one acknowledged emit at a time,
 * so an unsubscribe never overtakes a subscribe still waiting on the server's permission check.
 */
function syncRoom(key) {
	const room = rooms.get(key)
	if (!room || room.busy) return
	if (!currentSocket?.connected) {
		if (!room.count) rooms.delete(key)
		return
	}
	const wanted = room.count > 0
	if (wanted === room.joined) {
		if (!wanted) rooms.delete(key)
		return
	}
	room.busy = true
	const generation = connectionGeneration
	emitWithAck(currentSocket, wanted ? room.subscribe : room.unsubscribe, () => {
		if (generation !== connectionGeneration) return
		room.busy = false
		room.joined = wanted
		syncRoom(key)
		runReconnectHandlersWhenJoined()
	})
}

function emitWithAck(socket, args, done) {
	if (typeof socket.timeout !== "function") {
		socket.emit(...args)
		done()
		return
	}
	socket.timeout(ROOM_ACK_TIMEOUT_MS).emit(...args, () => done())
}

function runReconnectHandlersWhenJoined() {
	if (pendingReconnect === null || pendingReconnect !== connectionGeneration) return
	for (const room of rooms.values()) if (room.count && !room.joined) return
	pendingReconnect = null
	for (const handler of [...reconnectHandlers]) handler()
}

function resetRooms() {
	for (const [key, room] of rooms) {
		room.joined = false
		room.busy = false
		if (!room.count) rooms.delete(key)
	}
}

function countLiveRooms() {
	let count = 0
	for (const room of rooms.values()) if (room.count) count += 1
	liveRoomCount.value = count
}

function withSocket(run) {
	getSocket().then(run, () => {})
}
