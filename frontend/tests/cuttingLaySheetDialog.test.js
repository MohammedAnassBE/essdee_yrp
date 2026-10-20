import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"
import { computed, defineComponent, h, nextTick, reactive, ref, watch } from "vue"

function setup(props, { createGate = null } = {}) {
	const calls = []
	const source = fs.readFileSync(new URL("../src/departments/cutting/CuttingLaySheetDialog.vue", import.meta.url), "utf8").split("<script setup>")[1].split("</script>")[0].replace(/^import .*$/gm, "")
	const callMethod = async (method, args) => {
		const name = method.split(".").pop()
		calls.push({ method: name, args })
		if (name === "create_web_laysheet" && createGate) await createGate
		if (name === "create_web_laysheet") return { name: "CLS-1", cutting_marker: "CM-1", permissions: {} }
		if (name === "get_web_laysheet") {
			if (!args.cutting_laysheet) throw new Error("SD YRP Cutting LaySheet not found")
			return { name: args.cutting_laysheet, cutting_marker: "CM-1", status: "Bundles Generated", permissions: {} }
		}
	}
	const api = new Function("computed", "defineComponent", "h", "reactive", "ref", "watch", "defineProps", "defineEmits", "callMethod", "getQzPrinters", "printQzRaw", "useActionConfirmation", `${source}\nreturn { createForm, createLaySheet, generateBundles, generationParts, runStatusAction, sheet, error, actionError, loading }`)(
		computed, defineComponent, h, reactive, ref, watch, () => props, () => () => {}, callMethod, async () => [], async () => {}, () => () => {},
	)
	return { ...api, calls }
}

test("actions after creating a Lay Sheet reload the created sheet, not the empty prop name", async () => {
	const props = reactive({ visible: false, cuttingPlan: "CP-1", parentDoctype: "SD YRP Cutting Plan", parentName: "", laysheetName: "", canCreate: true })
	const state = setup(props)
	props.visible = true
	await nextTick()
	Object.assign(state.createForm, { cutting_marker: "CM-1", cutting_spreader: "Spreader", cutter: "Cutter" })
	await state.createLaySheet()
	state.generationParts.value = [{ part: "Front", value: 1 }]
	await state.generateBundles()
	await state.runStatusAction("approve_grammage", "approve")
	const reloads = state.calls.filter((call) => call.method === "get_web_laysheet").map((call) => call.args.cutting_laysheet)
	assert.deepEqual(reloads, ["CLS-1", "CLS-1"])
	assert.equal(state.calls.find((call) => call.method === "get_cut_sheet_data").args.doc_name, "CLS-1")
	assert.equal(state.sheet.value?.name, "CLS-1")
	assert.equal(state.error.value, "")
	assert.equal(state.actionError.value, "")
})

test("opening an existing Lay Sheet loads the prop name", async () => {
	const props = reactive({ visible: false, cuttingPlan: "CP-1", parentDoctype: "SD YRP Cutting Plan", parentName: "", laysheetName: "CLS-9", canCreate: true })
	const state = setup(props)
	props.visible = true
	await nextTick()
	await new Promise((resolve) => setTimeout(resolve, 0))
	assert.deepEqual(state.calls.map((call) => [call.method, call.args.cutting_laysheet]), [["get_web_laysheet", "CLS-9"]])
	assert.equal(state.sheet.value?.name, "CLS-9")
})

test("a create response arriving after reopening another Lay Sheet is ignored", async () => {
	let releaseCreate
	const createGate = new Promise((resolve) => { releaseCreate = resolve })
	const props = reactive({ visible: false, cuttingPlan: "CP-1", parentDoctype: "SD YRP Cutting Plan", parentName: "", laysheetName: "", canCreate: true })
	const state = setup(props, { createGate })
	props.visible = true
	await nextTick()
	Object.assign(state.createForm, { cutting_marker: "CM-1", cutting_spreader: "Spreader", cutter: "Cutter" })
	const creating = state.createLaySheet()
	props.visible = false
	await nextTick()
	props.laysheetName = "CLS-9"
	props.visible = true
	await nextTick()
	releaseCreate()
	await creating
	await new Promise((resolve) => setTimeout(resolve, 0))
	assert.equal(state.sheet.value?.name, "CLS-9")
	assert.equal(state.loading.value, false)
})
