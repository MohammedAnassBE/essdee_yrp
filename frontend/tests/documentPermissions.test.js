import assert from "node:assert/strict"
import test from "node:test"
import { effectScope, nextTick, reactive } from "vue"
import { useDocumentPermissions } from "../src/composables/useDocumentPermissions.js"

const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }
test("document actions share pending permission reads and recheck after status changes", async () => {
	const state = reactive({ name: "SHARED-1", status: 0 })
	const scope = effectScope()
	const calls = []
	let resolveRequest
	const fetch = (...args) => { calls.push(args); return new Promise(resolve => { resolveRequest = resolve }) }
	const [print, remove] = scope.run(() => [
		useDocumentPermissions(() => ["Test Doc", state.name, state.status], () => true, fetch),
		useDocumentPermissions(() => ["Test Doc", state.name, state.status], () => true, fetch),
	])
	await tick()
	assert.deepEqual(calls, [["Test Doc", "SHARED-1"]])
	resolveRequest({ print: 1, delete: 1 })
	await tick()
	assert.equal(print.value.print, 1)
	assert.equal(remove.value.delete, 1)
	state.status = 1
	await tick()
	assert.equal(calls.length, 2)
	assert.equal(print.value, null)
	resolveRequest({ print: 1, delete: 0 })
	await tick()
	assert.equal(remove.value.delete, 0)
	scope.stop()
})
test("permission loader skips absent identities and explicit permissions, drops stale responses, fails closed", async () => {
	const state = reactive({ name: "", enabled: true })
	const scope = effectScope()
	const resolvers = []
	const fetch = () => new Promise((resolve, reject) => resolvers.push({ resolve, reject }))
	const permissions = scope.run(() => useDocumentPermissions(() => ["Test Doc", state.name, 0], () => state.enabled, fetch))
	await tick()
	assert.equal(resolvers.length, 0)
	state.name = "OLD"
	await tick()
	state.name = "NEW"
	await tick()
	resolvers[0].resolve({ print: 1 })
	await tick()
	assert.equal(permissions.value, null)
	resolvers[1].reject(new Error("Forbidden"))
	await tick()
	assert.equal(permissions.value, null)
	state.enabled = false
	state.name = "EXPLICIT"
	await tick()
	assert.equal(resolvers.length, 2)
	scope.stop()
})
