import { onScopeDispose } from "vue"

import { onReconnect } from "../../api/realtime.js"
import { coalesceRefetch } from "./useBackgroundData.js"
import { useLivePause } from "./useLivePause.js"

/**
 * Calls `refetch()` when the page comes back into view (tab visible again, or KeepAlive reactivated)
 * after at least `minAwayMs`, and after a socket reconnect once every held room is joined again,
 * when live events may have been missed. `refetch` must be a background (silent) load.
 * Calls never overlap: one arriving mid-run queues one rerun. A refetch due while out of view,
 * including a queued rerun, waits for the return. `stop()` (also on scope dispose) cancels queued work.
 *
 * @param {() => unknown | Promise<unknown>} refetch
 * @param {{ minAwayMs?: number }} [options]
 * @returns {{ stop: () => void }}
 */
export function useRefetchOnReturn(refetch, { minAwayMs = 30_000 } = {}) {
	let stopped = false
	let owed = false
	const run = coalesceRefetch(() => {
		if (stopped) return
		if (pause.isPaused()) {
			owed = true
			return
		}
		return refetch()
	})
	const pause = useLivePause((awayMs) => {
		if (awayMs < minAwayMs && !owed) return
		owed = false
		run()
	})
	const offReconnect = onReconnect(() => {
		if (pause.isPaused()) owed = true
		else run()
	})

	function stop() {
		if (stopped) return
		stopped = true
		owed = false
		run.cancel()
		pause.stop()
		offReconnect()
	}
	onScopeDispose(stop)
	return { stop }
}
