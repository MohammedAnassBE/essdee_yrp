import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import {
	cutPanelReportTabs,
	cuttingReportTabs,
	finishingReportTabs,
	hrReportTabs,
	merchReportTabs,
	qualityReportTabs,
	salesReportTabs,
	sewingReportTabs,
	storeReportTabs,
} from "../src/departments/departmentReports.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const values = (tabs) => tabs.map((tab) => tab.value)
const readable = (...keys) => Object.fromEntries(keys.map((key) => [key, { can_read: true }]))

test("Cutting reports follow the per-report permission map and add Desk reports", () => {
	assert.deepEqual(values(cuttingReportTabs({ "multi-ccr": true, "daily-production": false, "grn-report": true })), ["multi-ccr", "grn-report"])
})

test("Merch & Purchase joins Merch and Purchase Desk reports once", () => {
	const reports = readable("work_in_progress", "grn_report", "purchase_order_log")
	assert.deepEqual(values(merchReportTabs("merch", reports)), ["work-in-progress", "grn-report"])
	assert.deepEqual(values(merchReportTabs("merch-purchase", reports)), ["work-in-progress", "grn-report", "purchase-order-log"])
})

test("each department lists only readable reports", () => {
	assert.deepEqual(values(finishingReportTabs(readable("packing_dpr", "dc_report"))), ["packing-dpr", "dc-report"])
	assert.deepEqual(values(qualityReportTabs(readable("lot_cut_quantity"))), ["lot-cut-quantity"])
	assert.deepEqual(values(hrReportTabs(readable("attendance"))), ["attendance"])
	assert.deepEqual(values(sewingReportTabs(readable("dpr", "finishing_inward_updates"))), ["dpr", "finishing-inward-updates"])
	assert.deepEqual(values(cutPanelReportTabs(readable("cut_bundle_balance"))), ["cut-bundle-balance"])
})

test("Sales reports need the Reports section", () => {
	assert.deepEqual(values(salesReportTabs({ sections: {}, reports: readable("ppo_report") })), [])
	assert.deepEqual(values(salesReportTabs({ sections: readable("reports"), reports: readable("ppo_report") })), ["ppo-report"])
})

test("store reports keep to the store's report keys", () => {
	const reports = readable("stock_balance", "lot_cut_quantity", "grn_report")
	assert.deepEqual(values(storeReportTabs(reports, "fabric-store", ["stock_balance"])), ["stock-balance", "grn-report"])
	assert.deepEqual(values(storeReportTabs({ grn_report: { can_read: true } }, "fabric-store", ["stock_balance"])), [])
})

test("report pages and launchers share these lists", () => {
	for (const page of [
		"../src/departments/CuttingReports.vue",
		"../src/departments/merch/MerchReports.vue",
		"../src/departments/finishing/FinishingReports.vue",
		"../src/departments/quality/QualityReports.vue",
		"../src/departments/hr/HrReports.vue",
		"../src/departments/sales/SalesReports.vue",
		"../src/departments/sewing/SewingReportsWorkspace.vue",
		"../src/departments/fabric-store/FabricReports.vue",
		"../src/departments/cut-panel-store/CutPanelStoreReports.vue",
	]) assert.match(source(page), /departmentReports\.js/, page)
	for (const launcher of ["Cutting", "Merch", "Finishing", "Quality", "HR", "Accounts", "Planning", "FabricStore", "CutPanelStore"]) {
		assert.match(source(`../src/departments/${launcher}.vue`), /:reports="/, launcher)
	}
	assert.match(source("../src/departments/sales/SalesLauncher.vue"), /:reports="/)
	assert.match(source("../src/departments/sewing/SewingLauncher.vue"), /:reports="/)
})
