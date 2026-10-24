let socketPromise = null
let listenerCount = 0

/** Resolves the shared socket; socket.io-client loads on first use, so pages without background jobs skip it. */
export function getSocket() {
	if (socketPromise) return socketPromise
	socketPromise = import("socket.io-client").then(({ io }) => {
		const boot = window.frappe?.boot || {}
		const origin = boot.dev_server
			? `${window.location.protocol}//${window.location.hostname}:${boot.socketio_port}`
			: window.location.origin
		return io(`${origin}/${boot.site_name}`, {
			autoConnect: false,
			withCredentials: true,
			reconnectionAttempts: 5,
		})
	})
	socketPromise.catch(() => { socketPromise = null })
	return socketPromise
}

export function onRealtime(event, handler) {
	let subscribed = true
	let connection = null
	listenerCount += 1
	getSocket().then((socket) => {
		if (!subscribed) return
		connection = socket
		socket.on(event, handler)
		if (!socket.connected && !socket.active) socket.connect()
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
