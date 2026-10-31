import { ref, shallowRef } from "vue"

/**
 * Wraps `fn` so calls never overlap: a call during a run queues exactly one rerun after it
 * and shares its promise. Rejections are logged, never thrown, so it is safe for event handlers.
 * `run.cancel()` drops a queued rerun and makes later calls no-ops (call it on unmount).
 * @param {() => unknown | Promise<unknown>} fn
 * @returns {(() => Promise<void>) & { cancel: () => void }}
 */
export function coalesceRefetch(fn) {
	let running = null
	let queued = null
	let cancelled = false
	async function runOnce() {
		try {
			await fn()
		} catch (error) {
			console.error("Background refetch failed", error)
		}
	}
	function run() {
		if (cancelled) return Promise.resolve()
		if (queued) return queued
		if (running) {
			queued = running.then(() => {
				queued = null
				return run()
			})
			return queued
		}
		running = runOnce().finally(() => { running = null })
		return running
	}
	run.cancel = () => { cancelled = true }
	return run
}

/**
 * Loads data with `fetcher(options)` and keeps the last result on screen during background refreshes.
 * - `load()`: foreground; sets `loading`, a failure sets `error` and clears `data`.
 * - `refresh()`: background; sets `refreshing` only, keeps `data`, a failure sets `refreshError` and keeps `data`.
 * A newer load or refresh supersedes the response of an older one; overlapping refreshes coalesce.
 * A refresh asked for during a load runs once after it succeeds, since the load may have read older data.
 * `fetcher` receives `{ background: boolean }`.
 *
 * @template T
 * @param {(options: { background: boolean }) => Promise<T>} fetcher
 * @param {{ initialData?: T }} [options]
 */
export function useBackgroundData(fetcher, { initialData = null } = {}) {
	const data = shallowRef(initialData)
	const loading = ref(false)
	const refreshing = ref(false)
	const error = ref(null)
	const refreshError = ref(null)
	let sequence = 0
	let refreshAfterLoad = false

	async function load() {
		const current = ++sequence
		loading.value = true
		error.value = null
		refreshError.value = null
		let loaded = false
		try {
			const result = await fetcher({ background: false })
			if (current === sequence) {
				data.value = result
				loaded = true
			}
		} catch (reason) {
			if (current !== sequence) return
			error.value = reason
			data.value = initialData
			refreshAfterLoad = false
		} finally {
			if (current === sequence) loading.value = false
		}
		if (loaded && refreshAfterLoad) {
			refreshAfterLoad = false
			await refresh()
		}
	}

	const refresh = coalesceRefetch(async () => {
		if (loading.value) {
			refreshAfterLoad = true
			return
		}
		const current = ++sequence
		refreshing.value = true
		try {
			const result = await fetcher({ background: true })
			if (current !== sequence) return
			data.value = result
			refreshError.value = null
		} catch (reason) {
			if (current === sequence) refreshError.value = reason
		} finally {
			refreshing.value = false
		}
	})

	return { data, loading, refreshing, error, refreshError, load, refresh }
}
