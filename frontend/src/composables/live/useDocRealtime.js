import { onScopeDispose, toValue, watch } from "vue"

import { onRealtime, subscribeDoc } from "../../api/realtime.js"
import { useLivePause } from "./useLivePause.js"

/**
 * Watches one saved document for changes made elsewhere (another user, tab or server job).
 *
 * Frappe's `doc_update` payload is `{ doctype, name, modified }` with no user, so an echo of this
 * page's own save is recognised the way Desk does it: `payload.modified === localModified()`.
 * While `isBusy()` is true (e.g. saving) the latest event is held and re-checked once it turns false,
 * because the event can arrive before the save response carries the new `modified`.
 * Events are also held while the page is KeepAlive-deactivated or the tab is hidden.
 *
 * @param {string | import("vue").MaybeRefOrGetter<string>} doctype
 * @param {import("vue").MaybeRefOrGetter<string>} name falsy (new document) subscribes to nothing
 * @param {{
 *   onRemoteChange: (payload: { doctype: string, name: string, modified: string }) => void,
 *   localModified: import("vue").MaybeRefOrGetter<string>,
 *   isBusy?: import("vue").MaybeRefOrGetter<boolean>,
 * }} options
 * @returns {{ stop: () => void }}
 */
export function useDocRealtime(doctype, name, { onRemoteChange, localModified, isBusy = false }) {
	let release = null
	let pending = null
	let stopped = false
	const pause = useLivePause(() => deliver())

	const stopWatch = watch(() => [toValue(doctype), toValue(name)], ([nextDoctype, nextName]) => {
		release?.()
		release = nextDoctype && nextName ? subscribeDoc(nextDoctype, nextName) : null
		pending = null
	}, { immediate: true })
	const stopBusyWatch = watch(() => toValue(isBusy), (busy) => { if (!busy) deliver() })

	const off = onRealtime("doc_update", (payload) => {
		if (stopped || payload?.doctype !== toValue(doctype) || payload?.name !== toValue(name)) return
		pending = payload
		deliver()
	})

	function deliver() {
		if (stopped || !pending || pause.isPaused() || toValue(isBusy)) return
		const payload = pending
		pending = null
		if (String(payload.modified ?? "") === String(toValue(localModified) ?? "")) return
		onRemoteChange(payload)
	}

	function stop() {
		if (stopped) return
		stopped = true
		pending = null
		pause.stop()
		stopWatch()
		stopBusyWatch()
		off()
		release?.()
		release = null
	}
	onScopeDispose(stop)
	return { stop }
}
