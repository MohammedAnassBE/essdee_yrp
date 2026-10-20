import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { parse, compileScript } from "@vue/compiler-sfc"

const source = path => readFileSync(new URL(`../src/${path}.vue`, import.meta.url), "utf8")
const dialogs = [
	"components/documents/DocumentTransactionDialog",
	"departments/cutting/CpmTransactionDialog",
	"departments/cutting/CpmMovementDialog",
	"departments/cutting/CuttingMarkerDialog",
	"departments/cutting/CuttingLaySheetDialog",
	"departments/cut-panel-store/CutPanelMovementDialog",
	"departments/cut-panel-store/BoxStickerPrintDialog",
	"departments/cut-panel-store/ExcelStickerPrintDialog",
	"departments/cut-panel-store/CutBundleEditDialog",
]
for (const path of dialogs) test(`${path}: deletion closes and notifies the parent without navigating`, () => {
	const text = source(path)
	compileScript(parse(text).descriptor, { id: path, inlineTemplate: true })
	const button = text.match(/<DocumentDeleteButton\b[^>]*\/>/)[0]
	assert.match(button, /:redirect="false"/)
	assert.match(button, /v-if="(?:record|sheet|payload.record)\?\.name"/)
	assert.match(button, /@deleted="documentDeleted"/)
	const events = []
	const handler = text.match(/function documentDeleted\(\) \{([\s\S]*?)\n\}/)[1]
	const savedDraft = { value: { name: "CPM-1" } }
	new Function("emit", "savedDraft", handler)((...event) => events.push(event), savedDraft)
	if (path === "departments/cutting/CpmMovementDialog") assert.equal(savedDraft.value, null)
	assert.deepEqual(events, [["update:visible", false], ["changed"]])
})

test("WO, PO, DC, GRN, IPD and the three Lot pages retain shared Delete", () => {
	for (const path of ["FabricWorkOrder", "FabricPurchaseOrder", "fabric-store/DeliveryChallanWorkspace", "fabric-store/GoodsReceivedNoteWorkspace", "merch/ipd/IpdPage", "purchase/lot/LotPage", "planning/lot/LotPage", "merch/lot/MerchLotPage"]) {
		const text = source(`departments/${path}`)
		assert.match(text, /<FabricDocumentWorkspace\b/)
		assert.doesNotMatch(text, /:show-delete="false"|<DocumentDeleteButton/)
	}
})
test("pages with domain Delete retain exactly one source of Delete actions", () => {
	for (const path of ["sales/ProductionOrder", "hr/BillTracking", "accounts/PurchaseInvoice", "purchase/ItemPricePage", "merch/process-cost/ProcessCostPage"]) {
		const text = source(`departments/${path}`)
		assert.match(text, /:show-delete="false"/)
		assert.doesNotMatch(text, /<DocumentDeleteButton/)
	}
	for (const path of ["pd/ProductPage", "pd/ProductReleasePage", "pd/LotwiseItemProfitPage"]) {
		const text = source(`departments/${path}`)
		assert.doesNotMatch(text, /<DocumentDeleteButton|<FabricDocumentWorkspace/)
		assert.match(text, /(?:deleteVisible|pending|deleteTarget)/)
	}
})
test("embedded DC and GRN deletions refresh their parent and close", () => {
	for (const path of ["DeliveryChallanWorkspace", "GoodsReceivedNoteWorkspace"]) {
		const text = source(`departments/fabric-store/${path}`)
		assert.match(text, /@deleted="documentDeleted"/)
		const body = text.match(/function documentDeleted\(\) \{([\s\S]*?)\n\}/)[1]
		const events = []
		new Function("emit", "props", body)((...event) => events.push(event), { presentation: "embedded" })
		assert.deepEqual(events, [["changed", { deleted: true }], ["closed"]])
	}
})

test("D1–D7 page actions use the saved identity, status, and list destination", () => {
	for (const [path, doctype, destination] of [
		["CuttingPlan", "SD YRP Cutting Plan", ':redirect-to="backTo"'],
		["CuttingOrder", "SD YRP Cutting Order", 'redirect-to="/cutting/orders"'],
		["CuttingBulkLaySheet", "SD YRP Cutting Bulk Lay Sheets", 'redirect-to="/cutting/bulk-lay-sheets"'],
		["CuttingLaySheetPlanner", "SD YRP Cutting Laysheet Planner", 'redirect-to="/cutting/lay-sheet-planner"'],
		["finishing/FinishingPlan", "SD YRP Finishing Plan", ':redirect-to="backTo"'],
		["finishing/FinishingDispatch", "SD YRP Finishing Plan Dispatch", 'redirect-to="/finishing/dispatches"'],
		["purchase/ItemPage", "Item", 'redirect-to="/purchase/items"'],
	]) {
		const text = source(`departments/${path}`)
		compileScript(parse(text).descriptor, { id: path, inlineTemplate: true })
		const buttons = text.match(/<DocumentDeleteButton\b[^>]*\/>/g)
		assert.ok(buttons.length)
		for (const button of buttons) {
			assert.ok(button.includes(`doctype="${doctype}"`))
			assert.ok(button.includes(destination))
			assert.match(button, /:docstatus=/)
		}
		if (path === "CuttingPlan" || path === "CuttingOrder") {
			assert.equal(buttons.length, 2)
			assert.match(text, /#document-actions/)
		}
		if (path === "finishing/FinishingDispatch") assert.match(buttons[0], /v-if="dispatchId && record.name"/)
	}
})
test("P2–P7 and QZ dialogs offer generic print through the shared button", () => {
	for (const path of ["CuttingBulkLaySheet", "CuttingLaySheetPlanner", "cut-panel-store/CutPanelMovementDialog", "pd/components/LotwiseWorkspaceHeader", "purchase/ItemPage", "cut-panel-store/BoxStickerPrintDialog", "cut-panel-store/ExcelStickerPrintDialog", "cut-panel-store/CutBundleEditDialog"]) {
		const text = source(`departments/${path}`)
		assert.equal((text.match(/<DocumentPrintButton\b/g) || []).length, 1)
	}
})

test("Process Cost delegates print to its document workspace", () => {
	const text = source("departments/merch/process-cost/ProcessCostPage")
	assert.match(text, /<FabricDocumentWorkspace\b/)
	assert.doesNotMatch(text, /<DocumentPrintButton\b/)
	assert.match(text, /pending\.value = \{ action: "Delete"/)
})
