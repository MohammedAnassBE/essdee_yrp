import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { computed, nextTick, reactive, ref, watch } from "vue"

import { hasQuantityChanges, quantityDraft, quantityErrors, quantityPayload } from "../src/departments/cutting/lotTransferQuantities.js"

const read = (path) => fs.readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")
const script = (path) => read(path).split("<script setup>")[1].split("</script>")[0].replace(/^import .*$/gm, "")
const rows = [
	{ name: "ROW-RED", item: "CLOTH-RED", label: "Jersey · Red · 30", qty: 100, available: 100 },
	{ name: "ROW-BLUE", item: "CLOTH-BLUE", label: "Jersey · Blue · 30", qty: 40, available: 40 },
]

test("lot transfer quantity must be above zero and within the plan balance", () => {
	const draft = quantityDraft(rows)
	assert.deepEqual(quantityErrors(draft), {})
	draft[0].qty = 0
	draft[1].qty = 40.001
	const errors = quantityErrors(draft)
	assert.match(errors["ROW-RED"], /greater than zero/)
	assert.match(errors["ROW-BLUE"], /Only 40 is available/)
	draft[0].qty = null
	assert.match(quantityErrors(draft)["ROW-RED"], /greater than zero/)
})

test("rows sharing one cloth variant are checked against the combined balance", () => {
	const shared = [{ ...rows[0], qty: 60 }, { ...rows[0], name: "ROW-RED-2", qty: 50 }]
	assert.equal(Object.keys(quantityErrors(shared)).length, 2)
	shared[1].qty = 40
	assert.deepEqual(quantityErrors(shared), {})
})

test("quantity changes and deleted rows are detected and sent as name and qty only", () => {
	const draft = quantityDraft(rows)
	assert.equal(hasQuantityChanges(rows, draft), false)
	draft[0].qty = 50
	assert.equal(hasQuantityChanges(rows, draft), true)
	assert.equal(hasQuantityChanges(rows, [quantityDraft(rows)[0]]), true)
	assert.deepEqual(quantityPayload(draft), [{ name: "ROW-RED", qty: 50 }, { name: "ROW-BLUE", qty: 40 }])
})

function editor(record, api = async () => record) {
	const confirmations = [], emitted = [], calls = []
	const state = new Function("ref", "computed", "watch", "defineProps", "defineEmits", "useActionConfirmation", "updateLotTransferQuantities", "hasQuantityChanges", "quantityDraft", "quantityErrors", "quantityPayload", `${script("cutting/LotTransferQuantityEditor.vue")}\nreturn { draft, dirty, hasErrors, requestDelete, save, error }`)(
		ref, computed, watch, () => ({ cuttingPlan: "CP-1", record }), () => (...args) => emitted.push(args),
		() => (options) => confirmations.push(options),
		async (...args) => { calls.push(args); return api(...args) },
		hasQuantityChanges, quantityDraft, quantityErrors, quantityPayload,
	)
	return { ...state, confirmations, emitted, calls }
}

test("quantity editor deletes a row only after confirmation and blocks deleting the last row", async () => {
	const state = editor({ name: "LT-1", modified: "2026-10-23 10:00:00", quantity_rows: rows })
	state.requestDelete(state.draft.value[1])
	assert.equal(state.draft.value.length, 2)
	assert.equal(state.confirmations[0].acceptLabel, "Delete Row")
	state.confirmations[0].accept()
	assert.deepEqual(state.draft.value.map((row) => row.name), ["ROW-RED"])
	assert.equal(state.dirty.value, true)
	state.requestDelete(state.draft.value[0])
	assert.equal(state.confirmations.length, 1)
	assert.equal(state.draft.value.length, 1)
})

test("quantity editor saves the edited draft with the loaded modified stamp", async () => {
	const saved = { name: "LT-1", quantity_rows: [] }
	const state = editor({ name: "LT-1", modified: "2026-10-23 10:00:00", quantity_rows: rows }, async () => saved)
	await state.save()
	assert.equal(state.calls.length, 0)
	state.draft.value[0].qty = 50
	await state.save()
	assert.deepEqual(state.calls, [["CP-1", "LT-1", [{ name: "ROW-RED", qty: 50 }, { name: "ROW-BLUE", qty: 40 }], "2026-10-23 10:00:00"]])
	assert.deepEqual(state.emitted.at(-1), ["saved", saved])
	state.draft.value[0].qty = 0
	assert.equal(state.hasErrors.value, true)
	await state.save()
	assert.equal(state.calls.length, 1)
})

test("created Lot Transfer is announced so the plan can open it without a page reload", async () => {
	const emitted = []
	const api = new Function("ref", "computed", "reactive", "defineProps", "defineEmits", "callMethod", "copyElementAsImage", "window", "watch", "onBeforeUnmount", `${script("cutting/CuttingPlanActions.vue")}\nreturn { targetLot, saveLotTransfer, feedback }`)(
		ref, computed, reactive, () => ({ doc: { name: "CP-1", lot: "LOT-A" }, data: {} }), () => (...args) => emitted.push(args),
		async () => "LT-9", () => {}, { setTimeout: () => 0, clearTimeout: () => {} }, watch, () => {},
	)
	api.targetLot.value = "LOT-B"
	await api.saveLotTransfer()
	assert.deepEqual(emitted, [["refresh"], ["lot-transfer-created", "LT-9"]])
	assert.match(api.feedback.value, /LT-9 created as Draft/)
	assert.match(read("CuttingPlan.vue"), /@lot-transfer-created="openLotTransfer"/)
	assert.match(read("CuttingPlan.vue"), /openTransaction\(\{ doctype: "SD YRP Lot Transfer", name \}, "lot_transfer"\)/)
	assert.match(read("cutting/CuttingPlanTabs.vue"), /defineExpose\(\{ activate, openTransaction \}\)/)
})

test("stock transfers open the created record and force a reload even while a load is running", async () => {
	const requests = []
	let release
	const state = new Function("ref", "reactive", "computed", "watch", "nextTick", "onMounted", "onBeforeUnmount", "defineProps", "defineEmits", "defineExpose", "getCpmWorkspace", `${script("cutting/CuttingPlanStockTransfers.vue")}\nreturn { load, showTransaction, activeTab, transactionOpen, selectedTransaction, workspace }`)(
		ref, reactive, computed, watch, nextTick, () => {}, () => {}, () => ({ cuttingPlan: "CP-1" }), () => () => {}, () => {},
		(name) => { requests.push(name); return requests.length === 1 ? new Promise((resolve) => { release = resolve }) : Promise.resolve({ transactions: { lot_transfer: [{ name: "LT-9" }] } }) },
	)
	const stale = state.load()
	await state.showTransaction({ doctype: "SD YRP Lot Transfer", name: "LT-9" }, "lot_transfer")
	release({ transactions: {} })
	await stale
	assert.equal(requests.length, 2)
	assert.equal(state.activeTab.value, "lot_transfer")
	assert.equal(state.transactionOpen.value, true)
	assert.equal(state.selectedTransaction.value.name, "LT-9")
	assert.deepEqual(state.workspace.transactions.lot_transfer, [{ name: "LT-9" }])
})

test("transaction dialog shows the quantity editor and blocks Submit with unsaved quantities", () => {
	const source = read("cutting/CpmTransactionDialog.vue")
	assert.match(source, /<LotTransferQuantityEditor v-if="record\?\.quantity_rows\?\.length"/)
	assert.match(source, /label="Submit" icon="pi pi-check" :disabled="quantityDirty"/)
})
