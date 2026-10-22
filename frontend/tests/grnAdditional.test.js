import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { additionalGrnFieldState, additionalGrnSourceContext } from "../src/departments/fabric-store/grnAdditional.js"

const workspaceSource = readFileSync(new URL("../src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue", import.meta.url), "utf8")

test("Additional GRN checkbox shows on Work Order receipts and is editable only before the first save", () => {
	assert.deepEqual(additionalGrnFieldState({ against: "YRP Work Order", isNew: true, canEditDraft: true }), { visible: true, editable: true })
	assert.deepEqual(additionalGrnFieldState({ against: "YRP Work Order", isNew: false, canEditDraft: true }), { visible: true, editable: false })
	assert.deepEqual(additionalGrnFieldState({ against: "YRP Work Order", isNew: true, canEditDraft: false }), { visible: true, editable: false })
	assert.deepEqual(additionalGrnFieldState({ against: "Purchase Order", isNew: true, canEditDraft: true }), { visible: false, editable: false })
	assert.deepEqual(additionalGrnFieldState({ against: "YRP Work Order", isReturn: 1, isNew: true, canEditDraft: true }), { visible: false, editable: false })
	assert.deepEqual(additionalGrnFieldState({ against: "YRP Work Order", isRework: "1", isNew: true, canEditDraft: true }), { visible: false, editable: false })
})

test("Toggling Additional GRN re-previews the same source with the flag", () => {
	const source = { work_order: "WO-1", delivery_challan: "DC-1" }
	assert.deepEqual(additionalGrnSourceContext(source, true), { work_order: "WO-1", delivery_challan: "DC-1", additional_grn: 1 })
	assert.deepEqual(additionalGrnSourceContext(source, 0), { work_order: "WO-1", delivery_challan: "DC-1", additional_grn: 0 })
	assert.deepEqual(source, { work_order: "WO-1", delivery_challan: "DC-1" })
})

test("GRN workspace renders the Additional GRN checkbox and reloads rows when it changes", () => {
	assert.match(workspaceSource, /additionalGrnFieldState\(/)
	assert.match(workspaceSource, /if \(fieldname === "additional_grn" && !currentName\.value\) return reloadAdditionalGrnSource\(value\)/)
	assert.match(workspaceSource, /getGoodsReceivedNoteWorkspace\("", additionalGrnSourceContext\(/)
	assert.match(workspaceSource, /fields: \["naming_series", "against", "against_id", "delivery_challan", "production_detail", "is_return", "is_rework", "additional_grn"\]/)
	assert.match(workspaceSource, /v-if="workspace\.special_source\?\.read_only" class="goods-received-note-special-context"/)
})

test("Additional GRN rows can add Received Type splits like a regular GRN", () => {
	assert.match(workspaceSource, /v-if="block\.kind === 'items' && canEditDraft && !workspace\.special_source\?\.read_only" label="Add split"/)
})
