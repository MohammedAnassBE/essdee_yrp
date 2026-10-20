import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"
import { linkFieldTarget } from "../src/utils/linkTarget.js"
import { computed, defineComponent, h, nextTick, reactive, ref, watch } from "vue"

function setup(props, { createGate = null } = {}) {
	const calls = []
	const confirmations = []
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
	const api = new Function("computed", "defineComponent", "h", "reactive", "ref", "watch", "defineProps", "defineEmits", "callMethod", "getQzPrinters", "printQzRaw", "useActionConfirmation", `${source}\nreturn { createForm, createLaySheet, generateBundles, generationParts, runStatusAction, sheet, error, actionError, loading, success, revertLabels, laysheetOverviewFields }`)(
		computed, defineComponent, h, reactive, ref, watch, () => props, () => () => {}, callMethod, async () => [], async () => {}, () => options => confirmations.push(options),
	)
	return { ...api, calls, confirmations }
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

test("action feedback survives the reload that follows the action", async () => {
	const props = reactive({ visible: false, cuttingPlan: "CP-1", parentDoctype: "SD YRP Cutting Plan", parentName: "", laysheetName: "CLS-1", canCreate: false })
	const state = setup(props)
	props.visible = true
	await nextTick()
	await new Promise((resolve) => setTimeout(resolve, 0))
	state.generationParts.value = [{ part: "Front", value: 1 }]
	await state.generateBundles()
	assert.equal(state.success.value, "Bundles generated.")
	await state.runStatusAction("approve_grammage", "approve")
	assert.equal(state.success.value, "Grammage approved.")
})


test("reverted Lay Sheet offers Update Status with the existing action", () => {
	const source = fs.readFileSync(new URL("../src/departments/cutting/CuttingLaySheetDialog.vue", import.meta.url), "utf8")
	assert.match(source, /<Button[^>]*can_restore_labels[^>]*label="Update Status"[^>]*@click="runStatusAction\('update_label_print_status', 'restore'\)"/)
	assert.doesNotMatch(source, /Restore Label Status/)
})

test("Revert Labels confirms GRN and bundle ledger cancellation before changing status", async () => {
	for (const grn of ["GRN-1", ""]) {
		const state = setup(reactive({ visible: false, cuttingPlan: "CP-1", parentDoctype: "SD YRP Cutting Plan" }))
		state.sheet.value = { name: "CLS-1", goods_received_note: grn }
		state.revertLabels()
		assert.deepEqual(state.calls, [])
		assert.equal(state.confirmations[0].header, "Revert labels?")
		assert.equal(state.confirmations[0].acceptLabel, "Revert Labels")
		assert.equal(state.confirmations[0].message, `Revert labels for CLS-1? This cancels ${grn ? "Goods Received Note GRN-1 and " : ""}the bundle ledger; labels must be updated again.`)
		await state.confirmations[0].accept()
		assert.deepEqual(state.calls[0], { method: "revert_labels", args: { doc_name: "CLS-1" } })
	}
	const source = fs.readFileSync(new URL("../src/departments/cutting/CuttingLaySheetDialog.vue", import.meta.url), "utf8")
	assert.match(source, /label="Revert Labels"[^>]*@click="revertLabels"/)
})

test("Lay Sheet overview links carry the target DocTypes", () => {
	const state = setup(reactive({ visible: false }))
	state.sheet.value = { cutting_spreader: "SP-1", cutter: "CUT-1", approved_by: "user@example.com", goods_received_note: "GRN-1" }
	for (const [fieldname, doctype] of Object.entries({ cutting_spreader: "SD YRP Cutting Spreader", cutter: "SD YRP Cutter", approved_by: "User", goods_received_note: "YRP Goods Received Note" })) {
		const field = state.laysheetOverviewFields.value.find(field => field.fieldname === fieldname)
		assert.deepEqual(linkFieldTarget(field), { doctype, name: state.sheet.value[fieldname] })
	}
})
