import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"

const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
function setup() {
	const route = { params: { cuttingPlanId: "CP-1" } }, probes = [], calls = []
	const source = fs.readFileSync(new URL("../src/departments/CuttingPlan.vue", import.meta.url), "utf8").split("<script setup>")[1].split("</script>")[0].replace(/^import .*$/gm, "")
	const api = new Function("ref", "computed", "watch", "useRoute", "useRouter", "defineProps", "getCuttingPlanEditor", "callMethod", "useDuplicateAction", "PLANNING_ROUTES", `${source}\nreturn { probeEditor, documentLoaded, documentSaved, editorSaved, retryWorkspace, workspaceData, workspaceReady, workspaceError, currentDocument, checkingEditor }`)(
		(value) => ({ value }), (fn) => ({ get value() { return fn() } }), () => {}, () => route, () => ({}), () => ({}),
		() => { const d = deferred(); probes.push(d); return d.promise },
		(method, args) => { const d = deferred(); calls.push({ ...d, method, args }); return d.promise },
		() => ({ value: null }), {},
	)
	return { ...api, route, calls, probes }
}

test("submitted view overlaps form loading and consumes one request; saves refresh", async () => {
	const state = setup(), probe = state.probeEditor()
	state.probes[0].resolve({ record: { docstatus: 1 }, permissions: {} }); await probe
	assert.equal(state.calls.length, 1)
	const loaded = state.documentLoaded({ name: "CP-1" })
	assert.equal(state.calls.length, 1)
	state.calls[0].resolve({ total: 7 }); await loaded
	assert.equal(state.workspaceData.value.total, 7)
	const saved = state.documentSaved({ name: "CP-1" })
	assert.equal(state.calls.length, 2)
	state.calls[1].resolve({ total: 8 }); await saved
	assert.equal(state.workspaceData.value.total, 8)
})

test("drafts never prefetch view; rejected probe falls back to the form", async () => {
	const state = setup(), probe = state.probeEditor()
	state.probes[0].resolve({ record: { docstatus: 0 }, permissions: { can_write: true } }); await probe
	assert.equal(state.calls.length, 0)
	const failed = state.probeEditor(); state.probes[1].reject(new Error("denied")); await failed
	assert.equal(state.checkingEditor.value, false)
	const loaded = state.documentLoaded({ name: "CP-1" }); state.calls[0].resolve({ fallback: true }); await loaded
	assert.equal(state.workspaceData.value.fallback, true)
})

test("route changes discard old data and rejected read-ahead retries", async () => {
	const state = setup(), first = state.probeEditor()
	state.probes[0].resolve({ record: { docstatus: 1 } }); await first
	const oldLoad = state.documentLoaded({ name: "CP-1" })
	state.route.params.cuttingPlanId = "CP-2"
	const second = state.probeEditor(); state.probes[1].resolve({ record: { docstatus: 1 } }); await second
	state.calls[0].resolve({ stale: true }); await oldLoad
	assert.deepEqual(state.workspaceData.value, {})
	const load = state.documentLoaded({ name: "CP-2" }); state.calls[1].reject(new Error("offline")); await load
	assert.equal(state.workspaceError.value, "offline")
	const retry = state.retryWorkspace(); state.calls[2].resolve({ fresh: true }); await retry
	assert.equal(state.workspaceData.value.fresh, true)
	const remount = state.documentLoaded({ name: "CP-2" }); await remount
	assert.equal(state.calls.length, 3)
})

test("submitted editor save discards an unconsumed initial view", async () => {
	const state = setup(), probe = state.probeEditor()
	state.probes[0].resolve({ record: { docstatus: 1 }, permissions: { can_update_after_submit: true } }); await probe
	state.editorSaved({ name: "CP-1", docstatus: 1 })
	const loaded = state.documentLoaded({ name: "CP-1" })
	const count = state.calls.length
	state.calls.forEach((call, index) => call.resolve({ total: index + 1 }))
	await loaded
	assert.equal(count, 2)
	assert.equal(state.workspaceData.value.total, 2)
})
