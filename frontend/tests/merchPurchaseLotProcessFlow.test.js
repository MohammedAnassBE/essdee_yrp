import assert from "node:assert/strict"
import { readdirSync, readFileSync } from "node:fs"
import test from "node:test"

import { LOT_TABS, LOT_VIEW_TABS } from "../src/departments/merch-purchase/lot/lotLayout.js"
import { reportPrefill } from "../src/utils/lotProcessFlow.js"

const folder = new URL("../src/departments/merch-purchase/lot/", import.meta.url)
const source = (path) => readFileSync(new URL(path, folder), "utf8")

test("Merch & Purchase view shows a Summary tab with the process flow; the editor keeps the Lot tab", () => {
	assert.equal(LOT_VIEW_TABS[0].label, "Summary")
	assert.equal(LOT_TABS[0].label, "Lot")
	const page = source("MerchLotPage.vue")
	assert.match(page, /<Tab v-for="tab in LOT_VIEW_TABS"/)
	assert.match(page, /expanded\.value = \[\.\.\.expanded\.value, "process-flow"\]/)
	assert.match(page, /back-to="\/merch-purchase\/lots"/)
	const view = source("LotViewMain.vue")
	assert.match(view, /import LotProcessFlow from "\.\/flow\/LotProcessFlow\.vue"/)
	assert.match(view, /:pieces="workspace\.order_pieces"/)
	assert.doesNotMatch(view, /LotOcrTable|#fabric-details|#ipd|#ppo/)
})

test("Merch & Purchase flow uses its own reports and nothing from another workspace's lot folder", () => {
	const flow = new URL("flow/", folder)
	for (const name of readdirSync(flow)) {
		const text = readFileSync(new URL(name, flow), "utf8")
		assert.doesNotMatch(text, /departments\/(merch|planning)\/lot|\.\.\/\.\.\/\.\.\/(merch|planning)\/lot/, name)
	}
	const container = source("flow/LotProcessFlow.vue")
	assert.match(container, /getMerchPurchaseCapabilities/)
	assert.match(container, /merchReportTabs\("merch-purchase", capabilities\?\.reports/)
	assert.match(source("flow/LotFlowReports.vue"), /const REPORTS_PATH = "\/web\/merch-purchase\/reports"/)
})

test("Purchase desk reports get the Lot and the Lot's date, never the garment Item or production Supplier", () => {
	const context = { lot: "L1", item: "VEST", process: "Stitching", supplier: "S-1", from_date: "2026-08-19", lot_date: "2026-06-16" }
	const params = (key) => Object.fromEntries(reportPrefill({ key }, context).map((filter) => [filter.param, filter.value]))
	assert.deepEqual(params("jobwork_issued_items"), { lot: "L1", from_date: "2026-06-16" })
	assert.deepEqual(params("lot_consumption_report"), { lot: "L1", start_date: "2026-06-16" })
	assert.deepEqual(params("lot_purchase_summary"), { lot: "L1" })
	// Closed POs of the Lot stay visible: the Open/Closed filter is cleared.
	assert.deepEqual(params("purchase_order_itemwise"), { lot: "L1", open_status: "" })
	assert.deepEqual(params("purchase_order_log"), {})
	assert.deepEqual(params("stock_ageing"), {})
})

test("Stock Balance and Lot Cut Quantity take the Lot from a Lot link", () => {
	const params = (key) => Object.fromEntries(reportPrefill({ key }, { lot: "L1", item: "VEST", process: "Cutting" }).map((filter) => [filter.param, filter.value]))
	assert.deepEqual(params("stock_balance"), { lot: "L1" })
	assert.deepEqual(params("lot_cut_quantity"), { lot: "L1" })
	const reports = new URL("../src/components/reports/", import.meta.url)
	const stock = readFileSync(new URL("StockBalanceReport.vue", reports), "utf8")
	assert.match(stock, /useReportQueryPrefill\(linkedLot, \["lot"\]/)
	assert.match(stock, /filters\.dimensions = \{ \.\.\.filters\.dimensions, lot: \[\.\.\.linkedLot\.lot\] \}/)
	assert.match(stock, /dimensionsLoaded\.value = true\n\t\tapplyLinkedLot\(\)/)
	assert.match(readFileSync(new URL("LotCutQuantityReport.vue", reports), "utf8"), /useReportQueryPrefill\(linkedLot, \["lot"\], \(\) => \{ selectedLots\.value = \[\.\.\.linkedLot\.lot\]; generate\(\) \}\)/)
})

test("step cards show the progress ring tile instead of bars", () => {
	assert.match(source("flow/LotItemSteps.vue"), /<LotStepRing :meters="step.meters" :status="step.status" \/>/)
	assert.doesNotMatch(source("flow/LotItemSteps.vue"), /pf-meters/)
})
