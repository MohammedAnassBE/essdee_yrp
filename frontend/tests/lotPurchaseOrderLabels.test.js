import assert from "node:assert/strict"
import test from "node:test"
import { purchaseOrderOption } from "../src/departments/purchase/lot/lotPurchaseActions.js"

test("Purchase Order options keep the supplier in the label so supplier searches stay visible", () => {
	assert.deepEqual(purchaseOrderOption({ name: "PO-1", label: "Sri Tex" }), { value: "PO-1", label: "PO-1 · Sri Tex" })
	assert.deepEqual(purchaseOrderOption({ name: "PO-2", label: "PO-2" }), { value: "PO-2", label: "PO-2" })
	assert.deepEqual(purchaseOrderOption("PO-3"), { value: "PO-3", label: "PO-3" })
})

test("report pages open the report named by the route report query", async () => {
	const { chooseReport } = await import("../src/components/reports/reportWorkspace.js")
	const tabs = [{ value: "stock-balance" }, { value: "lot-purchase-summary" }]
	assert.equal(chooseReport(tabs, "lot-purchase-summary", ""), "lot-purchase-summary")
	assert.equal(chooseReport(tabs, "missing", ""), "stock-balance")
	assert.equal(chooseReport(tabs, undefined, "stock-balance"), "stock-balance")
	assert.equal(chooseReport([], "x", "stock-balance"), "")
})
