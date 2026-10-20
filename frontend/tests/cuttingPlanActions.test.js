import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"

function setup(doc) {
	const calls = []
	const source = fs.readFileSync(new URL("../src/departments/cutting/CuttingPlanActions.vue", import.meta.url), "utf8").split("<script setup>")[1].split("</script>")[0].replace(/^import .*$/gm, "")
	const api = new Function("ref", "computed", "reactive", "defineProps", "defineEmits", "callMethod", "copyElementAsImage", "window", `${source}\nreturn { runPlanAction, dialogError }`)(
		(value) => ({ value }), (fn) => ({ get value() { return fn() } }), (value) => value,
		() => ({ doc, data: {} }), () => () => {},
		async (method, args) => { calls.push({ method: method.split(".").pop(), args }) },
		() => {}, { setTimeout: () => 0, clearTimeout: () => {} },
	)
	return { ...api, calls }
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
