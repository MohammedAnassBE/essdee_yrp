import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"
import { computed, nextTick, reactive, ref, watch } from "vue"

import { useRowSelection } from "../src/components/common/childGrid/rowSelection.js"

// Calculate LaySheets follows its queued job over the socket; covered in livePopups.test.js.
const trackedJobStub = () => ({ isRunning: ref(false), run: (queue) => queue() })
const { LAYSHEET_JOB_RESULTS } = await import("../src/composables/useTrackedJob.js")

function setup(doc, browser = { setTimeout: () => 0, clearTimeout: () => {} }) {
	let unmount
	const calls = []
	const source = fs.readFileSync(new URL("../src/departments/cutting/CuttingPlanActions.vue", import.meta.url), "utf8").split("<script setup>")[1].split("</script>")[0].replace(/^import .*$/gm, "")
	const api = new Function("ref", "computed", "reactive", "defineProps", "defineEmits", "callMethod", "copyCompletedReportImage", "window", "watch", "onBeforeUnmount", "useRowSelection", "useTrackedJob", "LAYSHEET_JOB_RESULTS", `${source}\nreturn { runPlanAction, dialogError, feedback, showFeedback }`)(
		ref, computed, reactive,
		() => ({ doc, data: {} }), () => () => {},
		async (method, args) => { calls.push({ method: method.split(".").pop(), args }) },
		() => {}, browser, watch, callback => { unmount = callback }, useRowSelection, trackedJobStub, LAYSHEET_JOB_RESULTS,
	)
	return { ...api, calls, unmount }
}

test("plan actions send the loaded document name, not the name at mount", async () => {
	const doc = {}
	const state = setup(doc)
	doc.name = "CP-1"
	for (const action of ["generate", "fetch", "calculate"]) await state.runPlanAction(action)
	assert.equal(state.dialogError.value, "")
	assert.deepEqual(state.calls, [
		{ method: "get_cloth1", args: { cutting_plan: "CP-1" } },
		{ method: "fetch_received_cloth", args: { docname: "CP-1" } },
		{ method: "calculate_laysheets", args: { cutting_plan: "CP-1" } },
	])
})


test("plan feedback expires after four seconds, resets for new feedback, and clears on unmount", async () => {
	const timers = new Map(), delays = []
	let nextId = 0
	const state = setup({}, {
		setTimeout: (callback, delay) => { delays.push(delay); timers.set(++nextId, callback); return nextId },
		clearTimeout: id => timers.delete(id),
	})
	state.showFeedback("Saved")
	await nextTick()
	assert.deepEqual(delays, [4000])
	state.showFeedback("Updated")
	await nextTick()
	assert.equal(timers.size, 1)
	assert.equal(timers.has(1), false)
	timers.get(2)()
	await nextTick()
	assert.equal(state.feedback.value, "")
	assert.equal(timers.size, 0)
	state.showFeedback("Saved again")
	await nextTick()
	state.unmount()
	assert.equal(timers.size, 0)
	const source = fs.readFileSync(new URL("../src/departments/cutting/CuttingPlanActions.vue", import.meta.url), "utf8")
	assert.match(source, /\.plan-action-feedback\s*\{[^}]*pointer-events: none;/)
	assert.match(source, /\.plan-action-feedback :deep\(\.p-message-close-button\)\s*\{ pointer-events: auto;/)
})
