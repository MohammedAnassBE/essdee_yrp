import { onScopeDispose, readonly, ref, toValue, watch } from "vue"

import { getList } from "../api/frappe.js"
import { coalesceRefetch } from "./live/useBackgroundData.js"
import { useDocRealtime } from "./live/useDocRealtime.js"
import { useListRealtime } from "./live/useListRealtime.js"
import { useRefetchOnReturn } from "./live/useRefetchOnReturn.js"
import { isMissingDocumentError, isStaleDocumentError } from "../utils/documentLiveState.js"

const RETRY_DELAYS_MS = [2_000, 5_000, 15_000]

/**
 * Keeps one open, saved document in step with changes made elsewhere, the way Desk does.
 *
 * A remote save reloads silently through `reload` while the page is clean; while it is dirty
 * `state` becomes "modified" and the page shows a bar. A delete (seen through `list_update`, a
 * version check after reconnect/return, or a 404 on reload) sets `state` to "deleted".
 * A remote stamp stays pending until a reload has reconciled it: events during a reload or a busy
 * period are retried afterwards, never dropped.
 *
 * `reload({ discard })` must refetch in place and return `false` when it did not apply the response
 * (the page was edited or saved meanwhile); `discard` means the user chose to drop local edits.
 *
 * @param {{
 *   doctype: import("vue").MaybeRefOrGetter<string>,
 *   name: import("vue").MaybeRefOrGetter<string>,
 *   localModified: import("vue").MaybeRefOrGetter<string>,
 *   isDirty?: import("vue").MaybeRefOrGetter<boolean>,
 *   isBusy?: import("vue").MaybeRefOrGetter<boolean>,
 *   reload: (options: { discard: boolean }) => Promise<unknown>,
 * }} options
 */
export function useLiveDocument({ doctype, name, localModified, isDirty = false, isBusy = false, reload }) {
	const state = ref("")
	const remoteModified = ref("")
	const reloading = ref(false)
	let pending = false
	let deferred = false
	let failures = 0
	let retryTimer = null
	let checkOwed = false
	let disposed = false
	let running = null

	const isHeld = () => disposed || reloading.value || Boolean(toValue(isBusy))

	watch(() => [toValue(doctype), toValue(name)], () => {
		clear()
		checkOwed = false
	})
	watch(() => toValue(localModified), (next) => {
		if (next && next === remoteModified.value && state.value !== "deleted") clear()
	})
	// A declined reload waits for the state that declined it to change: busy → idle or dirty → clean.
	watch(() => Boolean(toValue(isDirty)), (dirty) => { if (!dirty) resume() })
	// Only outside work counts here; the end of this composable's own reload is handled in `refresh`.
	watch(() => disposed || Boolean(toValue(isBusy)), (held) => {
		if (held || reloading.value) return
		if (checkOwed) checkVersion()
		else resume()
	})

	useDocRealtime(doctype, name, { localModified, isBusy, onRemoteChange: (payload) => remoteChanged(payload.modified) })
	useListRealtime(() => (toValue(name) ? [toValue(doctype)] : []), ({ names, hasUnnamed }) => {
		if (hasUnnamed || names.includes(toValue(name))) checkVersion()
	})

	/** Compares the stored version with this page: catches deletes and anything missed while offline. */
	const checkVersion = coalesceRefetch(async () => {
		const requested = [toValue(doctype), toValue(name)]
		if (!requested[1] || state.value === "deleted") return
		if (isHeld()) {
			checkOwed = true
			return
		}
		checkOwed = false
		const rows = await getList(requested[0], { fields: ["name", "modified"], filters: [["name", "=", requested[1]]], pageLength: 1 })
		if (disposed || requested[0] !== toValue(doctype) || requested[1] !== toValue(name)) return
		if (!rows.length) state.value = "deleted"
		else if (rows[0].modified && rows[0].modified !== toValue(localModified)) remoteChanged(rows[0].modified)
	})
	useRefetchOnReturn(() => (toValue(name) ? checkVersion() : undefined))

	function remoteChanged(modified) {
		if (disposed || state.value === "deleted" || !toValue(name)) return
		if (modified && modified === toValue(localModified)) return
		remoteModified.value = modified || remoteModified.value
		pending = true
		failures = 0
		reconcile()
	}

	function resume() {
		if (deferred) {
			deferred = false
			pending = true
		}
		if (pending) reconcile()
	}

	function reconcile() {
		if (!pending || isHeld() || state.value === "deleted") return
		if (toValue(isDirty)) state.value = "modified"
		else refresh({ discard: false })
	}

	/** Background reload; `discard: true` (the default, a user choice) drops local edits. */
	function refresh({ discard = true } = {}) {
		clearTimeout(retryTimer)
		retryTimer = null
		if (running) {
			pending = true
			return running
		}
		running = runReload(discard).finally(() => {
			running = null
			if (disposed || isHeld()) return
			if (checkOwed) checkVersion()
			else if (pending && state.value !== "modified") reconcile()
		})
		return running
	}

	async function runReload(discard) {
		pending = false
		reloading.value = true
		try {
			const applied = await reload({ discard })
			if (disposed) return
			if (applied === false) {
				deferred = true
				if (toValue(isDirty)) state.value = "modified"
				return
			}
			failures = 0
			// A stamp that arrived during the reload left `pending` set: it gets its own pass.
			if (pending && remoteModified.value && remoteModified.value !== toValue(localModified)) return
			if (state.value !== "deleted") clear()
		} catch (reason) {
			if (disposed) return
			if (isMissingDocumentError(reason)) state.value = "deleted"
			else {
				if (toValue(isDirty)) state.value = "modified"
				scheduleRetry()
			}
		} finally {
			if (!disposed) reloading.value = false
		}
	}

	/** Failed reloads retry after 2 s, 5 s and 15 s; then the next event, return or manual Reload tries again. */
	function scheduleRetry() {
		deferred = true
		if (failures >= RETRY_DELAYS_MS.length) return
		retryTimer = setTimeout(() => {
			retryTimer = null
			if (!disposed) resume()
		}, RETRY_DELAYS_MS[failures++])
	}

	/** Returns true when a save failed because the document changed elsewhere; the bar then explains it. */
	function handleSaveError(reason) {
		if (!isStaleDocumentError(reason)) return false
		if (state.value !== "deleted") {
			state.value = "modified"
			pending = true
		}
		return true
	}

	function clear() {
		state.value = ""
		remoteModified.value = ""
		pending = false
		deferred = false
		failures = 0
		clearTimeout(retryTimer)
		retryTimer = null
	}

	onScopeDispose(() => {
		disposed = true
		clearTimeout(retryTimer)
		checkVersion.cancel()
	})

	return { state: readonly(state), remoteModified: readonly(remoteModified), reloading: readonly(reloading), refresh, handleSaveError, clear }
}
