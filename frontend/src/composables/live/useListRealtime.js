import { onScopeDispose, toValue, watch } from "vue"

import { onRealtime, subscribeDoctype } from "../../api/realtime.js"
import { useLivePause } from "./useLivePause.js"

const MAX_HELD_EVENTS = 500

/**
 * Batches Frappe `list_update` events (`{ doctype, name, user }`, sent after commit on insert, save,
 * submit, cancel and delete) for one or more doctypes into one debounced `onChange` call.
 * Includes this user's own changes: other tabs and server jobs act as the same user.
 * A burst is flushed at most `maxWaitMs` after its first event; events wait while the page is
 * KeepAlive-deactivated or the tab is hidden and flush on return.
 *
 * @param {import("vue").MaybeRefOrGetter<string | string[]>} doctypes
 * @param {(change: { names: string[], doctypes: string[], events: object[], hasUnnamed: boolean }) => void} onChange
 *   `hasUnnamed` is true when an event had no name (bulk import) or events were dropped: refetch the whole list.
 * @param {{ debounceMs?: number, maxWaitMs?: number }} [options]
 * @returns {{ stop: () => void }}
 */
export function useListRealtime(doctypes, onChange, { debounceMs = 500, maxWaitMs = 2_000 } = {}) {
	const releases = new Map()
	let events = []
	let overflowed = false
	let timer = null
	let firstEventAt = 0
	let stopped = false
	const pause = useLivePause(() => flush())
	const isPaused = pause.isPaused

	const stopWatch = watch(() => normalizeDoctypes(toValue(doctypes)), (next) => {
		for (const [doctype, release] of releases) {
			if (next.includes(doctype)) continue
			release()
			releases.delete(doctype)
		}
		for (const doctype of next) if (!releases.has(doctype)) releases.set(doctype, subscribeDoctype(doctype))
	}, { immediate: true })

	const off = onRealtime("list_update", (payload) => {
		if (stopped || !releases.has(payload?.doctype)) return
		if (!events.length) firstEventAt = Date.now()
		// A long hidden tab keeps a bounded batch; anything dropped forces a full refetch.
		if (events.length < MAX_HELD_EVENTS) events.push(payload)
		else overflowed = true
		schedule()
	})

	function schedule() {
		clearTimeout(timer)
		timer = isPaused() ? null : setTimeout(flush, Math.max(0, Math.min(debounceMs, firstEventAt + maxWaitMs - Date.now())))
	}

	function flush() {
		clearTimeout(timer)
		timer = null
		if (stopped || !events.length || isPaused()) return
		const batch = events
		const hasUnnamed = overflowed || batch.some((event) => !event.name)
		events = []
		overflowed = false
		onChange({
			names: [...new Set(batch.map((event) => event.name).filter(Boolean))],
			doctypes: [...new Set(batch.map((event) => event.doctype))],
			events: batch,
			hasUnnamed,
		})
	}

	function stop() {
		if (stopped) return
		stopped = true
		pause.stop()
		stopWatch()
		off()
		clearTimeout(timer)
		events = []
		overflowed = false
		for (const release of releases.values()) release()
		releases.clear()
	}
	onScopeDispose(stop)
	return { stop }
}

function normalizeDoctypes(value) {
	const list = Array.isArray(value) ? value : [value]
	return [...new Set(list.filter(Boolean))]
}
