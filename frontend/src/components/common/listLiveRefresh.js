import { onScopeDispose, ref, watch } from "vue"

import { coalesceRefetch } from "../../composables/live/useBackgroundData.js"
import { useListRealtime } from "../../composables/live/useListRealtime.js"
import { useRefetchOnReturn } from "../../composables/live/useRefetchOnReturn.js"

export const ROW_HIGHLIGHT_MS = 1600

/** Names that are new in `next` or whose `modified` changed since `previous`. */
export function changedRowNames(previous, next) {
	const before = new Map(previous.map((row) => [row.name, row.modified]))
	return next
		.filter((row) => !before.has(row.name) || before.get(row.name) !== row.modified)
		.map((row) => row.name)
}

/**
 * Applies a `name in [...]` refetch to the loaded rows in place: returned rows replace their old copy,
 * requested names that came back empty (deleted or no longer matching the filters) are removed.
 */
export function mergeChangedRows(rows, fetched, names) {
	const fresh = new Map(fetched.map((row) => [row.name, row]))
	const requested = new Set(names)
	return rows
		.filter((row) => !requested.has(row.name) || fresh.has(row.name))
		.map((row) => fresh.get(row.name) || row)
}

/** Re-points a selection at the refetched row objects and drops rows that are gone. */
export function keepSelection(selected, rows) {
	if (!selected.length) return selected
	const byName = new Map(rows.map((row) => [row.name, row]))
	return selected.map((row) => byName.get(row.name)).filter(Boolean)
}

/**
 * Keeps a list live: list_update events, a return to the page, a socket reconnect and `request()`
 * (manual refresh) queue a background refetch, held while `isHeld()` and run once the hold ends.
 * The hold is rechecked when each run starts and, through `canApply()`, before the caller applies its response.
 * `refetch(change, { canApply })` reloads only `change.names` unless `change.full`; it returns
 * false to keep the change queued for a later run.
 */
export function useListLiveRefresh({ doctype, isHeld, refetch }) {
	let pendingNames = new Set()
	let pendingFull = false
	let disposed = false

	const canRun = () => !disposed && !isHeld()

	const run = coalesceRefetch(async () => {
		if (!canRun() || (!pendingFull && !pendingNames.size)) return
		const change = { names: [...pendingNames], full: pendingFull }
		discardPending()
		const applied = await refetch(change, { canApply: canRun })
		if (applied === false && !disposed) queue(change)
	})

	function queue({ names = [], full = false }) {
		for (const name of names) pendingNames.add(name)
		pendingFull ||= full
	}

	function request(change) {
		queue(change)
		return run()
	}

	function discardPending() {
		pendingNames = new Set()
		pendingFull = false
	}

	useListRealtime(doctype, ({ names, hasUnnamed }) => request({ names, full: hasUnnamed }))
	useRefetchOnReturn(() => request({ full: true }))
	watch(canRun, (ready) => { if (ready) run() })
	onScopeDispose(() => {
		disposed = true
		run.cancel()
		discardPending()
	})

	return { request, discardPending }
}

/** Marks rows for a short highlight; `isHighlighted(name)` is reactive. */
export function useRowHighlight(durationMs = ROW_HIGHLIGHT_MS) {
	const names = ref(new Set())
	const timers = new Map()

	function mark(changed) {
		if (!changed.length) return
		const next = new Set(names.value)
		for (const name of changed) {
			next.add(name)
			clearTimeout(timers.get(name))
			timers.set(name, setTimeout(() => unmark(name), durationMs))
		}
		names.value = next
	}

	function unmark(name) {
		timers.delete(name)
		const next = new Set(names.value)
		next.delete(name)
		names.value = next
	}

	onScopeDispose(() => {
		for (const timer of timers.values()) clearTimeout(timer)
		timers.clear()
	})

	return { mark, isHighlighted: (name) => names.value.has(name) }
}
