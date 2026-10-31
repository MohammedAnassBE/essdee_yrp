const STATES = {
	connected: { tone: "connected", label: "", title: "Live updates connected" },
	connecting: { tone: "connecting", label: "Reconnecting…", shortLabel: "Reconnecting", title: "Reconnecting… live updates are paused" },
	offline: { tone: "offline", label: "Offline — data may be out of date", shortLabel: "Offline", title: "Offline — data may be out of date" },
}

/**
 * Top-bar connection state. Hidden while the page holds no live room (`hasLiveUse`):
 * pages without live data have nothing to go stale, and the socket reports "offline" before anything connects it.
 * The browser's own offline flag wins over the socket state, which notices a lost network late.
 */
export function getConnectionIndicator({ status, hasLiveUse, isBrowserOnline = true }) {
	if (!hasLiveUse) return null
	if (!isBrowserOnline) return STATES.offline
	return STATES[status] || STATES.offline
}
