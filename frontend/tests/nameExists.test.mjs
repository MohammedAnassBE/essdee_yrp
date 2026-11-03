import assert from "node:assert/strict"
import test from "node:test"
import { effectScope, nextTick, reactive } from "vue"
import { useNameExists } from "../src/composables/useNameExists.js"
import { createDebouncedSearch } from "../src/departments/pd/pdViews.js"
import { quickEntryNameField } from "../src/utils/quickEntry.js"

const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }

function setup(initial = {}) {
	const state = reactive({ name: "", enabled: true, ...initial })
	const calls = []
	const resolvers = []
	const timers = []
	const count = (doctype, filters) => { calls.push([doctype, filters]); return new Promise((resolve, reject) => resolvers.push({ resolve, reject })) }
	const schedule = (callback, delay) => { timers.push({ callback, delay }); return timers.length }
	const cancel = (id) => { timers[id - 1].cancelled = true }
	const flush = () => { for (const timer of timers.splice(0)) if (!timer.cancelled) timer.callback() }
	const scope = effectScope()
	const existingName = scope.run(() => useNameExists("Brand", () => state.name, { enabled: () => state.enabled, count, timers: { schedule, cancel } }))
	return { state, calls, resolvers, timers, flush, scope, existingName }
}

test("debounces typing and reports the existing name", async () => {
	const { state, calls, resolvers, timers, flush, scope, existingName } = setup()
	state.name = "Ac"
	await tick()
	state.name = " Acme "
	await tick()
	assert.equal(timers.at(-1).delay, 300)
	flush()
	await tick()
	assert.deepEqual(calls, [["Brand", [["name", "=", "Acme"]]]])
	resolvers[0].resolve(1)
	await tick()
	assert.equal(existingName.value, "Acme")
	state.name = "Acme New"
	await tick()
	assert.equal(existingName.value, "")
	flush()
	resolvers[1].resolve(0)
	await tick()
	assert.equal(existingName.value, "")
	scope.stop()
})

test("skips empty input and disabled (saved) documents", async () => {
	const { state, calls, flush, scope, existingName } = setup({ enabled: false })
	state.name = "Acme"
	await tick()
	flush()
	state.enabled = true
	state.name = "   "
	await tick()
	flush()
	await tick()
	assert.equal(calls.length, 0)
	assert.equal(existingName.value, "")
	scope.stop()
})

test("drops stale responses and hides failures", async () => {
	const { state, resolvers, flush, scope, existingName } = setup()
	state.name = "Old"
	await tick()
	flush()
	await tick()
	state.name = "New"
	await tick()
	flush()
	await tick()
	resolvers[0].resolve(1)
	await tick()
	assert.equal(existingName.value, "")
	resolvers[1].reject(new Error("offline"))
	await tick()
	assert.equal(existingName.value, "")
	scope.stop()
})

test("pd keeps its debounced search export", () => {
	assert.equal(typeof createDebouncedSearch, "function")
})

test("quick entry name field comes from autoname", () => {
	assert.equal(quickEntryNameField({ autoname: "field:uom_name" }), "uom_name")
	assert.equal(quickEntryNameField({ autoname: "Prompt" }), "__newname")
	assert.equal(quickEntryNameField({ naming_rule: "Set by user" }), "__newname")
	assert.equal(quickEntryNameField({ autoname: "naming_series:" }), "")
	assert.equal(quickEntryNameField({ autoname: "hash" }), "")
	assert.equal(quickEntryNameField(null), "")
})
