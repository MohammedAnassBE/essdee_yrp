import { io } from "socket.io-client"

let socket
let listenerCount = 0

export function getSocket() {
	if (socket) return socket
	const boot = window.frappe?.boot || {}
	const origin = boot.dev_server
		? `${window.location.protocol}//${window.location.hostname}:${boot.socketio_port}`
		: window.location.origin
	socket = io(`${origin}/${boot.site_name}`, {
		autoConnect: false,
		withCredentials: true,
		reconnectionAttempts: 5,
	})
	return socket
}

export function onRealtime(event, handler) {
	const connection = getSocket()
	connection.on(event, handler)
	listenerCount += 1
	if (!connection.connected && !connection.active) connection.connect()
	let subscribed = true
	return () => {
		if (!subscribed) return
		subscribed = false
		connection.off(event, handler)
		listenerCount = Math.max(0, listenerCount - 1)
	}
}

export function hasRealtimeListeners() {
	return listenerCount > 0
}
