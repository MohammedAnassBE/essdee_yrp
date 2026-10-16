const TERMINAL_STATES = new Set(["ready", "expired", "error"])

export function envelopeState(envelope = {}) {
	if (envelope.expired || envelope.job?.status === "Expired") return "expired"
	const status = envelope.job?.status
	if (status === "Queued") return "queued"
	if (["Started", "Running"].includes(status)) return "running"
	if (status === "Error") return "error"
	if (status === "Completed" || envelope.mode === "sync") return "ready"
	return "idle"
}

export function pollingDelay(elapsedMilliseconds) {
	if (elapsedMilliseconds < 10_000) return 2_000
	if (elapsedMilliseconds < 60_000) return 5_000
	return 10_000
}

export function isTerminalReportState(state) {
	return TERMINAL_STATES.has(state)
}

export function isReportTrackingState(state) {
	return ["queued", "running"].includes(state)
}

export function createCancellableDelay() {
	let timer = null
	let settle = null

	function cancel() {
		if (timer !== null) clearTimeout(timer)
		timer = null
		settle?.(false)
		settle = null
	}

	function wait(milliseconds) {
		cancel()
		return new Promise((resolve) => {
			settle = resolve
			timer = setTimeout(() => {
				timer = null
				settle = null
				resolve(true)
			}, milliseconds)
		})
	}

	return { cancel, wait }
}

export function resumeStorageKey(reportKey) {
	return `yrp:web-report:${reportKey}`
}

export function shouldRemoveStoredTracking(state, preservePending) {
	return !preservePending || !["queued", "running"].includes(state)
}

export function normalizeReportFilters(filters = {}) {
	return normalizeFilterValue(filters)
}

export function sameReportFilters(left, right) {
	return JSON.stringify(normalizeReportFilters(left)) === JSON.stringify(normalizeReportFilters(right))
}

export function createStatusRequestQueue() {
	let generation = 0
	let tail = Promise.resolve()

	function invalidate() {
		generation += 1
		tail = Promise.resolve()
	}

	function run(request, accept) {
		const requestGeneration = generation
		const execution = tail.then(async () => {
			if (requestGeneration !== generation) return ignoredStatusRequest()
			const response = await request()
			if (requestGeneration !== generation) return ignoredStatusRequest()
			const terminal = Boolean(accept(response))
			if (terminal) invalidate()
			return { ignored: false, terminal }
		})
		tail = execution.catch(() => {})
		return execution
	}

	return { invalidate, run }
}

export function isDefinitiveReportError(reason) {
	const status = Number(reason?.status || reason?.response?.status || 0)
	return status >= 400 && status < 500 && ![408, 425, 429].includes(status)
}

function normalizeFilterValue(value) {
	if (value === null || value === undefined) return ""
	if (Array.isArray(value)) return value.map(normalizeFilterValue)
	if (typeof value !== "object") return value
	return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalizeFilterValue(value[key])]))
}

function ignoredStatusRequest() {
	return { ignored: true, terminal: false }
}

export function reportErrorMessage(reason) {
	const message = String(reason?.message || reason || "Unable to generate this report.")
	if (/background worker unavailable/i.test(message)) {
		return "Background processing is temporarily unavailable. Please ask an administrator to start a long-queue worker, then try again."
	}
	if (reason instanceof TypeError && /failed to fetch|networkerror|load failed/i.test(message)) {
		return "The report server did not respond. Narrow the filters or try again."
	}
	return message
}
