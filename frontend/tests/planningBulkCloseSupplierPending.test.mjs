import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"

import { PLANNING_ROUTES, PLANNING_WORKSPACES, visiblePlanningWorkspaces, visibleProductionReports } from "../src/departments/planning/planningViews.js"
import { planningReports } from "../src/departments/planning/reports/planningReportCatalog.js"
import { bulkCloseOutcome } from "../src/departments/planning/reports/workOrderBulkClose.js"
import { differenceTone, supplierPendingHint } from "../src/departments/planning/reports/supplierPending.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")

test("Planning shows a Bulk Close card on its own page", () => {
	const card = PLANNING_WORKSPACES.find((item) => item.key === "bulk_close")
	assert.equal(card.label, "Bulk Close")
	assert.equal(card.to, "/planning/bulk-close")
	assert.equal(PLANNING_WORKSPACES.findIndex((item) => item.key === "bulk_close"), PLANNING_WORKSPACES.findIndex((item) => item.key === "goods_received_notes") + 1)
	assert.deepEqual(visiblePlanningWorkspaces({ bulk_close: { can_read: true } }).map((item) => item.key), ["bulk_close"])
	assert.deepEqual(getWorkspacePaths(departments.find((item) => item.key === "planning")).bulk_close, ["/planning/bulk-close"])
	const router = source("../src/router/index.js")
	assert.match(router, /path: "\/planning\/bulk-close", name: PLANNING_ROUTES\.bulkClose, component: PlanningBulkClose/)
	assert.equal(PLANNING_ROUTES.bulkClose, "planning-bulk-close")
	assert.match(source("../src/departments/planning/PlanningBulkClose.vue"), /sections\?\.bulk_close/)
})

test("Supplier Pending Report sits under Planning reports and Bulk Close leaves them", () => {
	const reports = planningReports({ production: { supplier_pending: { can_read: true }, work_order_bulk_close: { can_read: true } } })
	assert.deepEqual(reports.map((report) => [report.label, report.value]), [["Supplier Pending Report", "supplier-pending"]])
	assert.ok(reports[0].component)
	assert.deepEqual(visibleProductionReports({ work_order_bulk_close: { can_read: true } }), [])
})

test("bulk close outcome lists every failed Work Order for the result dialog", () => {
	const results = [{ work_order: "WO-1", open_status: "Close" }, { work_order: "WO-2", open_status: "Close Request" }]
	assert.deepEqual(bulkCloseOutcome(results, [{ work_order: "WO-3", error: "No GRN" }]), {
		closed: 1, requested: 1, failed: [{ work_order: "WO-3", error: "No GRN" }],
		summary: "1 Work Order closed; 1 close request submitted.", failedLabel: "1 Work Order failed:",
	})
	const clean = bulkCloseOutcome([results[0], { work_order: "WO-4", open_status: "Close" }], [])
	assert.equal(clean.summary, "2 Work Orders closed; 0 close requests submitted.")
	assert.equal(clean.failed.length, 0)
	assert.equal(bulkCloseOutcome([], [{}, {}]).failedLabel, "2 Work Orders failed:")
})

test("Supplier Pending needs a supplier and a process and colours differences", () => {
	assert.equal(supplierPendingHint({ supplier: "", process: "Sewing" }), "Select a Supplier")
	assert.equal(supplierPendingHint({ supplier: "S", process: "" }), "Select a Process")
	assert.equal(supplierPendingHint({ supplier: "S", process: "Sewing" }), "")
	assert.equal(differenceTone(5, 10), "negative")
	assert.equal(differenceTone(10, 5), "positive")
	assert.equal(differenceTone(5, 5), "zero")
	assert.match(source("../src/departments/planning/reports/SupplierPendingReport.vue"), /formatDisplayDate/)
})

test("Supplier Pending Report renders lot rows, totals and DD-MM-YYYY dates", async () => {
	const tick = async () => { for (let index = 0; index < 5; index += 1) { await new Promise(done => setImmediate(done)); await Vue.nextTick() } }
	const value = (delivered, received) => ({ delivered, received, difference: received - delivered })
	const payload = { supplier: "S-1", supplier_name: "Unit One", items: [{ item: "Shirt", lots: [{
		lot: "LOT-1", is_set_item: false, primary_values: ["S", "M"],
		rows: [{ colour: "Red", part: null, values: { S: value(10, 2), M: value(5, 5) }, totals: value(15, 7), dates: { first_dc_date: "2026-01-04", last_dc_date: "2026-01-09", first_grn_date: "2026-02-01", last_grn_date: "2026-02-03", diff_days: 25 } }],
		totals: [{ part: null, values: { S: value(10, 2), M: value(5, 5) }, totals: value(15, 7) }],
	}] }] }
	let shell
	const calls = []
	const component = loadComponent(new URL("../src/departments/planning/reports/SupplierPendingReport.vue", import.meta.url).pathname, {
		"./supplierPending.js": { differenceTone, supplierPendingHint },
		"../../../composables/useReportQueryPrefill.js": { useReportQueryPrefill() {} },
		"../../../api/planning.js": { getSupplierPendingReport: async (...args) => { calls.push(args); return payload } },
		"../../../components/common/LinkField.vue": (props) => Vue.h("link", props),
		"../../../components/reports/ReportShell.vue": (props, { slots, attrs }) => { shell = { props, attrs }; return Vue.h("shell", props, [slots.filters?.(), slots.default?.()]) },
	})
	const root = mountComponent(component, {})
	try {
		await tick()
		const links = findNodes(root, (node) => node.type === "link")
		links[0].props["onUpdate:modelValue"]("S-1")
		links[1].props["onUpdate:modelValue"]("Sewing")
		await tick()
		await findNodes(root, (node) => node.type === "shell")[0].props.onGenerate()
		await tick()
		assert.deepEqual(calls, [["S-1", "Sewing"]])
		const text = findNodes(root, () => true).map((node) => node.text).join("|")
		for (const expected of ["Unit One", "Item: Shirt", "LOT-1", "Red", "04-01-2026", "03-02-2026", "Difference", "Total", "-8", "25"]) assert.ok(text.includes(expected), expected)
		assert.ok(!text.includes("2026-01-04"), "dates show as DD-MM-YYYY")
	} finally { root.__vue_app__.unmount() }
})
