import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { purchaseLotActions, lotPurchaseSummaryRoute, purchaseOrderLinkArgs, purchaseOrderLinkFilters } from "../src/departments/purchase/lot/lotPurchaseActions.js"
import { deskReportQueryFilters } from "../src/components/reports/deskReportConfig.js"

test("purchase lot offers summary to readers and PO actions only to writers", () => {
	const run = key => calls.push(key)
	const calls = []
	assert.deepEqual(purchaseLotActions({ name: "LOT-1" }, run).map(row => row.key), ["purchase_summary"])
	const actions = purchaseLotActions({ name: "LOT-1", permissions: { can_write: true } }, run)
	assert.deepEqual(actions.map(row => row.label), ["Edit", "Purchase Summary", "Link to PO", "Unlink from PO"])
	actions.forEach(row => row.command())
	assert.deepEqual(calls, actions.map(row => row.key))
	assert.ok(purchaseLotActions({ name: "LOT-1", permissions: { can_write: true } }, run, "reload").every(row => row.disabled))
	assert.deepEqual(purchaseLotActions({}, run), [])
	assert.deepEqual(lotPurchaseSummaryRoute("LOT / 1"), { path: "/purchase/reports", query: { report: "lot-purchase-summary", lot: "LOT / 1" } })
})

test("PO link policy and payload match Desk and preserve the reason", () => {
	assert.deepEqual(purchaseOrderLinkFilters(), { docstatus: 1, open_status: "Open" })
	assert.deepEqual(purchaseOrderLinkArgs("LOT-1", "link", ["PO-1"], " Reason "), { lot: "LOT-1", add_pos: ["PO-1"], remove_pos: [], comment: " Reason " })
	assert.deepEqual(purchaseOrderLinkArgs("LOT-1", "unlink", ["PO-2"], "Reason"), { lot: "LOT-1", add_pos: [], remove_pos: ["PO-2"], comment: "Reason" })
	assert.throws(() => purchaseOrderLinkArgs("LOT-1", "link", [], "Reason"), /Select at least one Purchase Order/)
	assert.throws(() => purchaseOrderLinkArgs("LOT-1", "link", ["PO-1"], "  "), /Reason is required/)
})

test("report query prefill only accepts configured filter fields and normalizes numeric filters", () => {
	assert.deepEqual(deskReportQueryFilters("lot-purchase-summary", { report: "lot-purchase-summary", lot: "LOT-1", unknown: "no", item: ["ITEM-1", "ITEM-2"] }), { lot: "LOT-1", item: "ITEM-1" })
	assert.deepEqual(deskReportQueryFilters("stock-ageing", { range1: "45", range2: "invalid", show_warehouse_wise_stock: "0", lot: null }), { range1: 45, show_warehouse_wise_stock: 0 })
	assert.deepEqual(deskReportQueryFilters("stock-ageing", { show_warehouse_wise_stock: "1" }), { show_warehouse_wise_stock: 1 })
	const source = readFileSync(new URL("../src/components/reports/DeskBackedReport.vue", import.meta.url), "utf8")
	assert.match(source, /deskReportQueryFilters\(props.reportKey, route.query\)/)
	assert.match(source, /watch\(\(\) => route.query/)
})
