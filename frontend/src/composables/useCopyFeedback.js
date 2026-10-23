import { onBeforeUnmount, ref } from "vue"
import { useToast } from "primevue/usetoast"

export const COPIED_RESET_MS = 1500

/** Shared Copy feedback: `copying` while it runs, then `copied` for 1.5 s plus a toast; failures toast the error, or a warning when one more click finishes the copy. */
export function useCopyFeedback({ success = "Copied to clipboard", toast = useToast(), timers = globalThis } = {}) {
	const copying = ref(false)
	const copied = ref(false)
	let resetTimer

	async function runCopy(copy) {
		if (copying.value) return false
		copying.value = true
		copied.value = false
		timers.clearTimeout(resetTimer)
		try {
			await copy()
			copied.value = true
			resetTimer = timers.setTimeout(() => { copied.value = false }, COPIED_RESET_MS)
			toast.add({ severity: "success", summary: success, life: 2500 })
			return true
		} catch (exception) {
			const retryable = Boolean(exception?.retryable)
			toast.add({ severity: retryable ? "warn" : "error", summary: retryable ? "Click Copy again" : "Copy failed", detail: exception?.message || "Could not copy to the clipboard.", life: 6000 })
			return false
		} finally {
			copying.value = false
		}
	}

	onBeforeUnmount(() => timers.clearTimeout(resetTimer))
	return { copying, copied, runCopy }
}
