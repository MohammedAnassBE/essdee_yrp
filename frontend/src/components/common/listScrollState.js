const KEY_PREFIX = "essdee-yrp:list-scroll:v1"
const memory = new Map()

/** Session-only memory of how far a list was loaded and scrolled, so returning from a document lands on the same rows. */
export function listScrollStateKey(routeName, doctype) {
	if (!routeName || !doctype) return ""
	return [KEY_PREFIX, routeName, doctype].map((part) => encodeURIComponent(String(part))).join(":")
}

/** Identifies the query a saved position belongs to; a position is only restored for the same query. */
export function listQueryFingerprint(query) {
	return JSON.stringify(query)
}

function sessionStore() {
	try {
		return globalThis.window?.sessionStorage || null
	} catch {
		return null
	}
}

function normalizedState(state) {
	if (!state || typeof state.fingerprint !== "string") return null
	return {
		fingerprint: state.fingerprint,
		loadedCount: Math.max(0, Math.floor(Number(state.loadedCount) || 0)),
		scrollTop: Math.max(0, Number(state.scrollTop) || 0),
	}
}

export function saveListScrollState(key, state, storage = sessionStore()) {
	const value = normalizedState(state)
	if (!key || !value) return
	memory.set(key, value)
	try {
		storage?.setItem(key, JSON.stringify(value))
	} catch {
		// Storage can be full or blocked; the in-memory copy still serves this tab.
	}
}

export function readListScrollState(key, fingerprint, storage = sessionStore()) {
	if (!key) return null
	let state = memory.get(key) || null
	if (!state) {
		try {
			state = normalizedState(JSON.parse(storage?.getItem(key) || "null"))
		} catch {
			state = null
		}
	}
	return state && state.fingerprint === fingerprint ? state : null
}

export function clearListScrollStates() {
	memory.clear()
}
