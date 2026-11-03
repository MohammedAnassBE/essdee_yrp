import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"

import { copyDocumentName, isCopyableDocumentName } from "../src/components/common/documentNameCopy.js"

const read = (path) => fs.readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("only saved document names are copyable", () => {
	assert.equal(isCopyableDocumentName("LOT-0001"), true)
	assert.equal(isCopyableDocumentName(42), true)
	assert.equal(isCopyableDocumentName(""), false)
	assert.equal(isCopyableDocumentName(null), false)
	assert.equal(isCopyableDocumentName("new-sd-yrp-lot-abc123"), false)
})

test("copyDocumentName copies the exact name and fails loudly", async () => {
	const copied = []
	await copyDocumentName("CLS-0042", async (text) => { copied.push(text); return true })
	await copyDocumentName(7, async (text) => { copied.push(text); return true })
	assert.deepEqual(copied, ["CLS-0042", "7"])
	await assert.rejects(copyDocumentName("CLS-0042", async () => false), /Could not copy CLS-0042/)
})

test("DocumentNameCopy is a keyboard accessible copy target with a Copied toast", () => {
	const source = read("components/common/DocumentNameCopy.vue")
	assert.match(source, /role="button"/)
	assert.match(source, /tabindex="0"/)
	assert.match(source, /title="Click to copy"/)
	assert.match(source, /@keydown\.enter\.prevent="copy"/)
	assert.match(source, /@keydown\.space\.prevent="copy"/)
	assert.match(source, /useCopyFeedback\(\{ success: "Copied" \}\)/)
	assert.match(source, /cursor: pointer/)
})

const HEADERS = [
	"departments/fabric-store/FabricDocumentWorkspace.vue",
	"departments/FabricPurchaseOrder.vue",
	"departments/FabricWorkOrder.vue",
	"departments/CuttingOrder.vue",
	"departments/CuttingBulkLaySheet.vue",
	"departments/CuttingLaySheetPlanner.vue",
	"departments/cutting/RecordDialogHeader.vue",
	"departments/finishing/FinishingPlan.vue",
	"departments/finishing/FinishingDispatch.vue",
	"departments/sales/ProductionOrder.vue",
	"departments/quality/QualityInspection.vue",
	"departments/hr/BillTracking.vue",
	"departments/accounts/components/PurchaseInvoiceHeader.vue",
	"departments/merch/process-cost/ProcessCostPage.vue",
	"departments/purchase/ItemPricePage.vue",
	"departments/purchase/ItemPage.vue",
	"departments/purchase/lot/LotIdentity.vue",
	"departments/merch/ipd/IpdIdentity.vue",
	"departments/fabric-store/DeliveryChallanWorkspace.vue",
	"departments/fabric-store/GoodsReceivedNoteWorkspace.vue",
	"departments/cut-panel-store/BoxStickerPrintPage.vue",
	"departments/pd/components/ProductWorkspaceHeader.vue",
	"departments/pd/ProductReleasePage.vue",
	"departments/pd/components/LotwiseWorkspaceHeader.vue",
	"components/common/FormView.vue",
]

test("every document page header uses DocumentNameCopy for its name", () => {
	for (const path of HEADERS) assert.match(read(path), /<DocumentNameCopy /, path)
})

test("lay sheet and marker dialogs pass the document name separately", () => {
	assert.match(read("departments/cutting/CuttingLaySheetDialog.vue"), /<RecordDialogHeader[^>]*title="sheet \? 'Lay Sheet' : 'Create Lay Sheet'"[^>]*:name="sheet\?\.name \|\| ''"/)
	assert.match(read("departments/cutting/CuttingMarkerDialog.vue"), /<RecordDialogHeader[^>]*:name="record\?\.name \|\| ''"/)
})
