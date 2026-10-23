import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { resolvePageTitle, routeTitle, singularLabel } from "../src/utils/pageTitle.js"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const departments = [
	{ key: "accessory-store", label: "Accessory Store", path: "/accessory-store" },
	{ key: "planning", label: "Planning", path: "/planning" },
]
const route = (path, params = {}, extra = {}) => ({ path, params, name: extra.name || "some-route", meta: extra.meta || {} })

test("document page shows only the document name, with no department or app prefix", () => {
	const title = routeTitle(route("/accessory-store/work-orders/YRP-WO-2026-00002", { workOrderId: "YRP-WO-2026-00002" }), departments)
	assert.equal(title, "YRP-WO-2026-00002")
	assert.equal(routeTitle(route("/planning/lots/LOT-001/edit", { lotId: "LOT-001" }), departments), "LOT-001")
})

test("list page shows the list label", () => {
	assert.equal(routeTitle(route("/accessory-store/work-orders"), departments), "Work Orders")
	assert.equal(routeTitle(route("/planning/cutting-plans"), departments), "Cutting Plans")
})

test("new document shows New <Doctype>", () => {
	assert.equal(routeTitle(route("/accessory-store/work-orders/new"), departments), "New Work Order")
	assert.equal(routeTitle(route("/finishing/dispatches/new"), departments), "New Dispatch")
	assert.equal(routeTitle(route("/merch/item-production-details/new"), departments), "New Item Production Detail")
	assert.equal(routeTitle(route("/hr/bill-tracking/new"), departments), "New Bill Tracking")
	assert.equal(singularLabel("Goods Received Notes"), "Goods Received Note")
})

test("department home, workspaces, reports and unknown paths", () => {
	assert.equal(routeTitle(route("/planning", {}, { name: "planning" }), departments), "Planning")
	assert.equal(routeTitle(route("/", {}, { name: "administrator" }), departments), "Workspaces")
	assert.equal(routeTitle(route("/planning/reports"), departments), "Reports")
	assert.equal(routeTitle(route("/nope/x", { pathMatch: ["nope", "x"] }), departments), "Not Found")
	assert.equal(routeTitle(route("/planning/x", {}, { meta: { title: "Custom" } }), departments), "Custom")
})

test("report and title-field pages report their own title for the current path only", () => {
	const reports = route("/planning/reports")
	assert.equal(resolvePageTitle(reports, departments, { path: "/planning/reports", title: "Lot Cut Quantity" }), "Lot Cut Quantity")
	const next = route("/finishing/plans/FP-0002", { finishingPlanId: "FP-0002" })
	assert.equal(resolvePageTitle(next, departments, { path: "/finishing/plans/FP-0001", title: "Old Item" }), "FP-0002")
	assert.equal(resolvePageTitle(next, departments, { path: "/finishing/plans/FP-0002", title: "New Item" }), "New Item")
	assert.equal(resolvePageTitle(next, departments, null), "FP-0002")
})

test("App.vue owns document.title through the shared resolver with no app suffix", () => {
	const app = read("App.vue")
	assert.match(app, /document\.title = resolvePageTitle\(route, departments, reportedPageTitle\.value\)/)
	assert.doesNotMatch(app, /Essdee YRP`/)
	assert.equal((app.match(/document\.title\s*=/g) || []).length, 1)
})

test("report workspace and title-field document pages use usePageTitle", () => {
	assert.match(read("components/reports/ReportWorkspace.vue"), /usePageTitle\(\(\) => current\.value\?\.label\)/)
	assert.match(read("departments/finishing/FinishingPlan.vue"), /usePageTitle\(\(\) => record\.value\.name, \(\) => record\.value\.item\)/)
	assert.match(read("departments/CuttingBulkLaySheet.vue"), /usePageTitle\(\(\) => record\.value\.name, \(\) => record\.value\.main_lot\)/)
	assert.match(read("departments/pd/LotwiseItemProfitPage.vue"), /usePageTitle\(\(\) => form\.value\.name, \(\) => form\.value\.item\)/)
	assert.match(read("departments/purchase/ItemPage.vue"), /usePageTitle\(.*values\.value\.name\)/)
	assert.match(read("departments/FabricPurchaseOrder.vue"), /usePageTitle\(.*supplier_name\)/)
})
