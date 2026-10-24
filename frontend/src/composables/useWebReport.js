import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from "vue"

import { onRealtime } from "../api/realtime.js"
import { downloadReportJob, getReportJob, runWebReport } from "../api/webReports.js"
import { normalizeReportRows } from "./reportColumns.js"
import {
	createCancellableDelay,
	createStatusRequestQueue,
	envelopeState,
	isDefinitiveReportError,
	isReportTrackingState,
	isTerminalReportState,
	normalizeReportFilters,
	pollingDelay,
	reportErrorMessage,
	resumeStorageKey,
	sameReportFilters,
	shouldRemoveStoredTracking,
} from "./webReportState.js"

export function useWebReport({ reportKey }) {
	const state = ref("idle")
	// Results are replaced as a whole and never mutated in place, so they are not deep-reactive.
	const sourceColumns = shallowRef([])
	const sourceRows = shallowRef([])
	const payload = shallowRef(null)
	const job = ref(null)
	const generatedAt = ref(null)
	const reused = ref(false)
	const error = ref("")
	const message = ref("")
	const reportSummary = ref(null)
	const mode = ref("")
	const trackingStartedAt = ref(null)
	const activeFilters = ref(null)
	let currentFilters = null
	let generation = 0
	let pollTimer
	let realtimeUnsubscribers = []
	const statusRequests = createStatusRequestQueue()
	const retryDelay = createCancellableDelay()

	const loading = computed(() => state.value === "loading")
	const isBusy = computed(() => ["loading", "queued", "running"].includes(state.value))
	const generated = computed(() => state.value === "ready")
	const isBackgroundResult = computed(() => Boolean(job.value && state.value === "ready"))
	const statusOnly = computed(() => ["queued", "running", "expired", "error"].includes(state.value))

	async function generate(filters, { refresh = false } = {}) {
		const requestGeneration = beginRequest(filters)
		try {
			const envelope = await runWebReport(reportKey, currentFilters, refresh)
			if (requestGeneration !== generation) return
			applyEnvelope(envelope)
			if (["queued", "running"].includes(state.value)) startTracking(requestGeneration)
		} catch (reason) {
			if (requestGeneration !== generation) return
			state.value = "error"
			error.value = reportErrorMessage(reason)
		}
	}

	function beginRequest(filters) {
		generation += 1
		stopTracking()
		currentFilters = normalizeReportFilters(filters)
		activeFilters.value = normalizeReportFilters(currentFilters)
		clearResult()
		state.value = "loading"
		return generation
	}

	function applyEnvelope(envelope = {}) {
		mode.value = envelope.mode || mode.value
		job.value = envelope.job || null
		sourceColumns.value = envelope.columns || []
		sourceRows.value = normalizeReportRows(envelope.result || [], sourceColumns.value)
		payload.value = envelope
		reportSummary.value = envelope.report_summary || null
		message.value = envelope.message || ""
		generatedAt.value = envelope.generated_at || envelope.job?.finished_at || null
		reused.value = Boolean(envelope.reused)
		state.value = envelopeState(envelope)
		if (state.value === "error") error.value = reportErrorMessage(envelope.message || envelope.error_message)
		if (["queued", "running"].includes(state.value)) persistTracking()
		else removeStoredTracking()
	}

	function startTracking(requestGeneration) {
		trackingStartedAt.value ||= Date.now()
		stopRealtime()
		realtimeUnsubscribers = [
			onRealtime("yrp_report_done", (event) => handleDone(event, requestGeneration)),
			onRealtime("yrp_report_progress", (event) => handleProgress(event, requestGeneration)),
			onRealtime("connect", () => pollNow(requestGeneration)),
		]
		schedulePoll(requestGeneration)
	}

	async function handleDone(event, requestGeneration) {
		if (!isCurrentJob(event, requestGeneration)) return
		await pollJob(requestGeneration, 3)
	}

	function handleProgress(event, requestGeneration) {
		if (!isCurrentJob(event, requestGeneration)) return
		job.value = { ...job.value, status: "Started", progress: Number(event.percent || 0) }
		state.value = "running"
	}

	function isCurrentJob(event, requestGeneration) {
		return requestGeneration === generation
			&& ["queued", "running"].includes(state.value)
			&& event?.job === job.value?.name
	}

	async function pollJob(requestGeneration, startedRetries = 0) {
		if (requestGeneration !== generation || !job.value?.name || !isReportTrackingState(state.value)) return
		const jobName = job.value.name
		try {
			const outcome = await statusRequests.run(
				() => getReportJob(reportKey, jobName, true),
				(envelope) => applyPolledEnvelope(envelope, requestGeneration, jobName),
			)
			if (outcome.ignored) return
			if (outcome.terminal) {
				stopTracking()
				return
			}
			await continuePolling(requestGeneration, startedRetries)
		} catch (reason) {
			if (requestGeneration !== generation) return
			if (isDefinitiveReportError(reason)) {
				state.value = "error"
				error.value = reportErrorMessage(reason)
				stopTracking()
				return
			}
			schedulePoll(requestGeneration)
		}
	}

	function applyPolledEnvelope(envelope, requestGeneration, jobName) {
		if (requestGeneration !== generation || jobName !== job.value?.name) return true
		applyEnvelope(envelope)
		return isTerminalReportState(state.value)
	}

	async function continuePolling(requestGeneration, startedRetries) {
		if (state.value === "running" && startedRetries > 0) {
			const shouldRetry = await retryDelay.wait(500)
			if (shouldRetry && requestGeneration === generation && isReportTrackingState(state.value)) {
				return pollJob(requestGeneration, startedRetries - 1)
			}
			return
		}
		schedulePoll(requestGeneration)
	}

	function schedulePoll(requestGeneration) {
		if (requestGeneration !== generation || !["queued", "running"].includes(state.value)) return
		window.clearTimeout(pollTimer)
		const elapsed = Date.now() - (trackingStartedAt.value || Date.now())
		pollTimer = window.setTimeout(() => pollJob(requestGeneration), pollingDelay(elapsed))
	}

	function pollNow(requestGeneration = generation) {
		window.clearTimeout(pollTimer)
		if (isReportTrackingState(state.value)) pollJob(requestGeneration)
	}

	function filtersChanged(filters) {
		if (!currentFilters || sameReportFilters(filters, currentFilters)) return
		clear()
	}

	function clear() {
		generation += 1
		stopTracking()
		currentFilters = null
		activeFilters.value = null
		clearResult()
		state.value = "idle"
	}

	function clearResult() {
		sourceColumns.value = []
		sourceRows.value = []
		payload.value = null
		job.value = null
		generatedAt.value = null
		reused.value = false
		error.value = ""
		message.value = ""
		reportSummary.value = null
		mode.value = ""
		trackingStartedAt.value = null
	}

	function stopTracking({ preservePending = false } = {}) {
		window.clearTimeout(pollTimer)
		retryDelay.cancel()
		statusRequests.invalidate()
		stopRealtime()
		if (shouldRemoveStoredTracking(state.value, preservePending)) removeStoredTracking()
	}

	function stopRealtime() {
		realtimeUnsubscribers.forEach((unsubscribe) => unsubscribe())
		realtimeUnsubscribers = []
	}

	function persistTracking() {
		if (!job.value?.name) return
		safeSessionStorage()?.setItem(resumeStorageKey(reportKey), JSON.stringify({
			reportKey,
			jobName: job.value.name,
			filters: currentFilters,
		}))
	}

	async function resumeStoredJob() {
		const storage = safeSessionStorage()
		const stored = parseStoredTracking(storage?.getItem(resumeStorageKey(reportKey)))
		if (!stored || stored.reportKey !== reportKey) return
		currentFilters = normalizeReportFilters(stored.filters)
		activeFilters.value = normalizeReportFilters(currentFilters)
		job.value = { name: stored.jobName, status: "Queued", progress: 0 }
		state.value = "queued"
		trackingStartedAt.value = Date.now()
		const requestGeneration = ++generation
		startTracking(requestGeneration)
		await pollJob(requestGeneration)
	}

	function removeStoredTracking() {
		safeSessionStorage()?.removeItem(resumeStorageKey(reportKey))
	}

	async function download() {
		if (!job.value?.name) return
		await downloadReportJob(reportKey, job.value.name)
	}

	function handleVisibility() {
		if (document.visibilityState === "visible" && ["queued", "running"].includes(state.value)) {
			pollNow()
		}
	}

	onMounted(() => {
		document.addEventListener("visibilitychange", handleVisibility)
		resumeStoredJob().catch((reason) => {
			state.value = "error"
			error.value = reportErrorMessage(reason)
		})
	})
	onBeforeUnmount(() => {
		document.removeEventListener("visibilitychange", handleVisibility)
		generation += 1
		stopTracking({ preservePending: true })
	})

	return {
		state,
		sourceColumns,
		sourceRows,
		payload,
		job,
		generatedAt,
		reused,
		error,
		message,
		reportSummary,
		mode,
		trackingStartedAt,
		activeFilters,
		loading,
		isBusy,
		generated,
		isBackgroundResult,
		statusOnly,
		generate,
		filtersChanged,
		clear,
		download,
		dispose: clear,
	}
}

function parseStoredTracking(value) {
	try {
		const parsed = JSON.parse(value)
		return parsed?.jobName ? parsed : null
	} catch {
		return null
	}
}

function safeSessionStorage() {
	try {
		return window.sessionStorage
	} catch {
		return null
	}
}

