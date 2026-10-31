import { getCurrentInstance, onActivated, onDeactivated, onScopeDispose } from "vue"

const isDocumentHidden = () => globalThis.document?.visibilityState === "hidden"

/**
 * Tracks whether the caller is out of view: its KeepAlive parent deactivated it or the browser tab is hidden.
 * `onResume(awayMs)` runs each time it comes back into view.
 * `stop()` (also run on scope dispose) ends it: no further `onResume` calls.
 * @returns {{ isPaused: () => boolean, stop: () => void }}
 */
export function useLivePause(onResume = () => {}) {
	let stopped = false
	let deactivated = false
	let pausedAt = isDocumentHidden() ? Date.now() : null
	const isPaused = () => deactivated || isDocumentHidden()

	function pause() {
		if (pausedAt === null) pausedAt = Date.now()
	}

	function resume() {
		if (stopped || isPaused() || pausedAt === null) return
		const awayMs = Date.now() - pausedAt
		pausedAt = null
		onResume(awayMs)
	}

	const onVisibilityChange = () => (isDocumentHidden() ? pause() : resume())
	if (getCurrentInstance()) {
		onDeactivated(() => { deactivated = true; pause() })
		onActivated(() => { deactivated = false; resume() })
	}
	globalThis.document?.addEventListener("visibilitychange", onVisibilityChange)
	function stop() {
		if (stopped) return
		stopped = true
		globalThis.document?.removeEventListener("visibilitychange", onVisibilityChange)
	}
	onScopeDispose(stop)
	return { isPaused, stop }
}
