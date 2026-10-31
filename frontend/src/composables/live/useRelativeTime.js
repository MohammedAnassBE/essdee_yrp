import { computed, getCurrentScope, onScopeDispose, ref, toValue } from "vue"

import { formatDisplayDate } from "../../utils/dateFormat.js"

const TICK_MS = 30_000
const DATETIME_PATTERN = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{1,2}))?)?/

const now = ref(Date.now())
let consumers = 0
let timer = null

/** "just now", "5 min ago", "3 h ago", else the DD-MM-YYYY date. Frappe datetimes are read as local time. */
export function formatRelativeTime(value, nowMs = Date.now()) {
	const time = toTimestamp(value)
	if (time === null) return ""
	const seconds = Math.floor((nowMs - time) / 1_000)
	if (seconds < 60) return "just now"
	if (seconds < 3_600) return `${Math.floor(seconds / 60)} min ago`
	if (seconds < 86_400) return `${Math.floor(seconds / 3_600)} h ago`
	return formatDisplayDate(new Date(time), "")
}

function toTimestamp(value) {
	if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value.getTime()
	if (typeof value === "number") return Number.isFinite(value) ? value : null
	const match = String(value ?? "").match(DATETIME_PATTERN)
	if (!match) return null
	const [, year, month, day, hour = 0, minute = 0, second = 0] = match.map((part) => part && Number(part))
	return new Date(year, month - 1, day, hour, minute, second).getTime()
}

/**
 * Reactive relative label for a timestamp (Frappe datetime string, Date or epoch ms).
 * All callers share one 30 s timer that runs only while at least one caller's scope is alive;
 * a call outside any effect scope gets a label that does not tick.
 * @param {import("vue").MaybeRefOrGetter<string | Date | number | null>} timestamp
 * @returns {import("vue").ComputedRef<string>}
 */
export function useRelativeTime(timestamp) {
	const label = computed(() => formatRelativeTime(toValue(timestamp), now.value))
	// Without a scope there is no dispose to stop the timer, so the label does not tick.
	if (!getCurrentScope()) return label
	startTicking()
	let disposed = false
	onScopeDispose(() => {
		if (disposed) return
		disposed = true
		stopTicking()
	})
	return label
}

function startTicking() {
	consumers += 1
	if (consumers > 1) return
	now.value = Date.now()
	timer = setInterval(() => { now.value = Date.now() }, TICK_MS)
	// Node only: a component a test never unmounts must not keep the process alive.
	timer?.unref?.()
}

function stopTicking() {
	consumers -= 1
	if (consumers > 0) return
	clearInterval(timer)
	timer = null
}
