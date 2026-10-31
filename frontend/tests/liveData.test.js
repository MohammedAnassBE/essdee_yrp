import assert from "node:assert/strict"
import test from "node:test"
import { effectScope, ref } from "vue"

const { coalesceRefetch, useBackgroundData } = await import("../src/composables/live/useBackgroundData.js")
const { formatRelativeTime, useRelativeTime } = await import("../src/composables/live/useRelativeTime.js")

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

function deferred() {
	let resolve, reject
	const promise = new Promise((done, fail) => { resolve = done; reject = fail })
	return { promise, resolve, reject }
}

test("formatRelativeTime reads Frappe datetimes as local time", () => {
	const now = new Date(2026, 9, 31, 12, 0, 0).getTime()
	assert.equal(formatRelativeTime("2026-10-31 11:59:30.123456", now), "just now")
	assert.equal(formatRelativeTime("2026-10-31 11:58:00", now), "2 min ago")
	assert.equal(formatRelativeTime("2026-10-31 09:00:00", now), "3 h ago")
	assert.equal(formatRelativeTime("2026-10-29 12:00:00", now), "29-10-2026")
	assert.equal(formatRelativeTime(new Date(now + 5_000), now), "just now", "small clock skew")
	assert.equal(formatRelativeTime(now - 120_000, now), "2 min ago")
	assert.equal(formatRelativeTime(null, now), "")
})

test("useRelativeTime shares one timer that stops with its last consumer", (t) => {
	t.mock.timers.enable({ apis: ["setInterval", "Date"], now: new Date(2026, 9, 31, 12, 0, 0) })
	const started = new Date(2026, 9, 31, 12, 0, 0)
	const first = effectScope()
	const second = effectScope()
	const labelA = first.run(() => useRelativeTime(started))
	const timestamp = ref("2026-10-31 11:00:00")
	const labelB = second.run(() => useRelativeTime(timestamp))
	assert.deepEqual([labelA.value, labelB.value], ["just now", "1 h ago"])
	t.mock.timers.tick(120_000)
	assert.equal(labelA.value, "2 min ago")
	timestamp.value = "2026-10-31 12:01:30"
	assert.equal(labelB.value, "just now")
	first.stop()
	t.mock.timers.tick(60_000)
	assert.equal(labelB.value, "1 min ago", "the timer keeps running for the remaining consumer")
	second.stop()
	const frozen = labelB.value
	t.mock.timers.tick(600_000)
	assert.equal(labelB.value, frozen)
})

test("coalesceRefetch never overlaps and queues exactly one rerun", async () => {
	const runs = []
	const coalesced = coalesceRefetch(() => { const gate = deferred(); runs.push(gate); return gate.promise })
	const first = coalesced()
	const second = coalesced()
	const third = coalesced()
	assert.equal(second, third)
	assert.equal(runs.length, 1)
	runs[0].reject(new Error("boom"))
	const originalError = console.error
	console.error = () => {}
	try {
		await first
		await flush()
	} finally {
		console.error = originalError
	}
	assert.equal(runs.length, 2, "a failed run still lets the queued rerun go")
	runs[1].resolve()
	await second
	assert.equal(runs.length, 2)
})

test("useBackgroundData keeps the data on screen during a refresh and a failed refresh", async () => {
	const responses = []
	const seen = []
	const store = useBackgroundData((options) => { seen.push(options.background); const gate = deferred(); responses.push(gate); return gate.promise }, { initialData: [] })
	const loading = store.load()
	assert.equal(store.loading.value, true)
	responses[0].resolve(["a"])
	await loading
	assert.deepEqual([store.data.value, store.loading.value], [["a"], false])

	const refresh = store.refresh()
	assert.deepEqual([store.refreshing.value, store.loading.value, store.data.value], [true, false, ["a"]])
	responses[1].reject(new Error("offline"))
	await refresh
	assert.deepEqual([store.data.value, store.refreshing.value, store.refreshError.value.message], [["a"], false, "offline"])

	const stale = store.refresh()
	const fresh = store.load()
	responses[3].resolve(["fresh"])
	await fresh
	responses[2].resolve(["stale"])
	await stale
	assert.deepEqual([store.data.value, store.refreshing.value, store.loading.value], [["fresh"], false, false], "a newer load wins")
	assert.deepEqual(seen, [false, true, true, false])
})

test("a refresh asked for during a pending load runs once after it", async () => {
	const responses = []
	const store = useBackgroundData((options) => { const gate = deferred(); responses.push({ gate, ...options }); return gate.promise })
	const loading = store.load()
	store.refresh()
	store.refresh()
	assert.equal(responses.length, 1)
	responses[0].gate.resolve(["old"])
	await flush()
	assert.deepEqual(responses.map((response) => response.background), [false, true])
	responses[1].gate.resolve(["new"])
	await loading
	assert.deepEqual(store.data.value, ["new"])
})

test("coalesceRefetch.cancel() drops a queued rerun and later calls", async () => {
	let runs = 0
	let finish
	const run = coalesceRefetch(() => { runs += 1; return new Promise((resolve) => { finish = resolve }) })
	run()
	const queued = run()
	run.cancel()
	finish()
	await queued
	run()
	assert.equal(runs, 1)
})

test("useRelativeTime outside an effect scope starts no timer", (t) => {
	t.mock.timers.enable({ apis: ["setInterval", "Date"], now: new Date(2026, 9, 31, 12, 0, 0) })
	const label = useRelativeTime(new Date(2026, 9, 31, 11, 0, 0))
	const before = label.value
	t.mock.timers.tick(7_200_000)
	assert.equal(label.value, before, "nothing ticks, so nothing can keep the process alive")
})
