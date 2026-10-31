import { onScopeDispose, ref } from "vue"

import { callRead } from "../api/frappe.js"
import { onRealtime } from "../api/realtime.js"

export const JOB_DONE_EVENT = "yrp_laysheet_job_done"
const STATUS_METHOD = "essdee_yrp.cutting.laysheet_jobs.get_tracked_job_status"
const TERMINAL_STATUSES = new Set(["finished", "failed"])

/**
 * Follows one server job queued through `essdee_yrp.cutting.laysheet_jobs`.
 * `run(queue)` calls `queue()`, which resolves to `{ job_token }`, then reports that job's own end:
 * `onDone("finished" | "failed")` from the job's realtime event, or from a status poll when the event was missed;
 * `onDone("timeout")` after `timeoutMs`; `onDone("unknown")` when the server no longer knows the job.
 * Saves of the document by anyone else never count as the end of the job.
 *
 * @param {{ onDone: (status: string) => void, pollMs?: number, timeoutMs?: number, getStatus?: (token: string) => Promise<{ status: string }> }} options
 */
export function useTrackedJob({ onDone, pollMs = 5_000, timeoutMs = 600_000, getStatus = getJobStatus }) {
	const isRunning = ref(false)
	let token = ""
	let timers = []
	let off = null
	let disposed = false
	// Events that arrive before the queuing response names this job's token.
	const early = new Map()

	async function run(queue) {
		stopTracking()
		isRunning.value = true
		off = onRealtime(JOB_DONE_EVENT, receive)
		try {
			const result = await queue()
			if (disposed || !isRunning.value) return result
			if (!result?.job_token) throw new Error("The server did not return a job token.")
			token = result.job_token
			if (early.has(token)) finish(early.get(token))
			else {
				early.clear()
				timers.push(setTimeout(() => finish("timeout"), timeoutMs))
				schedulePoll()
			}
			return result
		} catch (error) {
			stopTracking()
			throw error
		}
	}

	function receive(event) {
		if (!TERMINAL_STATUSES.has(event?.status) || !event.job_token) return
		if (event.job_token === token) finish(event.status)
		else if (!token) early.set(event.job_token, event.status)
	}

	function schedulePoll() {
		const polledToken = token
		timers.push(setTimeout(async () => {
			let status = ""
			try { status = (await getStatus(polledToken))?.status || "" }
			catch { status = "" }
			if (disposed || polledToken !== token) return
			if (TERMINAL_STATUSES.has(status) || status === "unknown") finish(status)
			else schedulePoll()
		}, pollMs))
	}

	function finish(status) {
		if (disposed || !isRunning.value) return
		stopTracking()
		onDone(status)
	}

	function stopTracking() {
		for (const timer of timers) clearTimeout(timer)
		timers = []
		off?.()
		off = null
		token = ""
		early.clear()
		isRunning.value = false
	}

	onScopeDispose(() => {
		disposed = true
		stopTracking()
	})
	return { isRunning, run }
}

function getJobStatus(jobToken) {
	return callRead(STATUS_METHOD, { job_token: jobToken })
}

/** What a LaySheet calculation's end means for the page: the message and whether its data changed. */
export const LAYSHEET_JOB_RESULTS = {
	finished: { message: "LaySheets calculated.", severity: "success", refresh: true },
	failed: { message: "LaySheet calculation failed. Nothing was changed; check the Error Log and try again.", severity: "error", refresh: false },
	timeout: { message: "LaySheet calculation has not reported back yet. Refresh later to see the result.", severity: "warn", refresh: false },
	unknown: { message: "LaySheet calculation status is unavailable. Refresh to see the latest result.", severity: "warn", refresh: false },
}
