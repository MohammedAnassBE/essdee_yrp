import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import {
	clothHeadline, colourSwatch, filterReports, reportsListHeight, diffTone, fabricSummary, itemHeadline, reportPrefill, stepReportContext, percent, reportHref, sizeTable, statusTone, workOrderHref,
} from "../src/utils/lotProcessFlow.js"

const source = (path) => readFileSync(new URL(`../src/departments/merch/lot/${path}`, import.meta.url), "utf8")

test("status tone: complete at 99.5%, partial above zero, not done at zero", () => {
	assert.equal(statusTone(995, 1000), "ok")
	assert.equal(statusTone(994, 1000), "part")
	assert.equal(statusTone(0, 1000), "none")
	assert.equal(statusTone(5, 0), "")
})

test("difference tone: matched or over is green, shortfall bands at 5% and 25%", () => {
	assert.equal(diffTone(0, 100), "d-ok")
	assert.equal(diffTone(3, 100), "d-ok")
	assert.equal(diffTone(-5, 100), "d-1")
	assert.equal(diffTone(-25, 100), "d-2")
	assert.equal(diffTone(-26, 100), "d-3")
	assert.equal(percent(14897, 15246), 97.7)
})

test("size table derives received tone from delivered, or planned when nothing was delivered", () => {
	const grid = [
		{ colour: "Red", part: "", planned: { S: 10, M: 10 }, delivered: { S: 10, M: 0 }, received: { S: 9, M: 0 } },
		{ colour: "Blue", part: "", planned: { S: 4 }, delivered: {}, received: { S: 4 } },
	]
	const table = sizeTable(grid, ["S", "M"], ["planned", "delivered", "received", "difference"])
	const [red, blue] = table.rows
	assert.deepEqual(red.lines.map((line) => line.key), ["planned", "delivered", "received", "difference"])
	assert.deepEqual(red.lines[2].cells.map((cell) => cell.tone), ["part", ""])
	assert.deepEqual(red.lines[3].cells.map((cell) => [cell.value, cell.tone]), [[-1, "d-2"], [0, ""]])
	assert.deepEqual(blue.lines[2].cells[0], { value: 4, tone: "ok" })
	assert.equal(blue.lines[3].total.value, 0)
	assert.equal(table.footer.find((line) => line.key === "planned").total.value, 24)
	assert.equal(sizeTable(grid.slice(0, 1), ["S"], ["planned"]).footer, null)
})

test("pending row tones only when pieces are still out", () => {
	const table = sizeTable([{ colour: "Red", part: "", planned: { S: 10 }, delivered: { S: 10 }, received: { S: 7 } }], ["S"], ["planned", "delivered", "received", "pending"])
	assert.deepEqual(table.rows[0].lines[3].cells[0], { value: 3, tone: "d-3" })
})

test("headlines name the furthest started step and finished cloth items", () => {
	const steps = [
		{ process: "Cutting", status: "done" },
		{ process: "Stitching", status: "partial" },
		{ process: "Packing", status: "idle" },
	]
	assert.equal(itemHeadline(steps), "At Stitching. 1 of 3 steps complete.")
	assert.equal(itemHeadline(steps.map((step) => ({ ...step, status: "idle" }))), "Not started yet.")
	assert.equal(clothHeadline([{ status: "done" }, { status: "partial" }]), "1 of 2 cloth items ready.")
})

test("work order and report links open Merch pages", () => {
	assert.equal(workOrderHref({ target: { doctype: "SD YRP Finishing Plan", name: "FP-1" } }, "/web/merch/lots/L1"), "/web/finishing/plans/FP-1")
	assert.equal(workOrderHref({ target: { doctype: "SD YRP Cutting Plan", name: "CP-1" } }, "/web/merch/lots/L1"), "/web/merch/cutting-plans/CP-1")
	assert.equal(workOrderHref({ target: { doctype: "YRP Work Order", name: "WO 1" } }, "/web/merch/lots/L1"), "/web/merch/work-orders/WO%201")
	const context = { lot: "L/1", item: "VEST", process: "Stitching", supplier: "S-1", from_date: "2026-08-12" }
	assert.equal(reportHref("/web/merch/reports", { key: "inhouse_quantity", value: "inhouse-quantity" }, context), "/web/merch/reports?report=inhouse-quantity&lot=L%2F1&process=Stitching")
	assert.equal(reportHref("/web/merch/reports", { key: "inward_quantity", value: "inward-quantity" }, context), "/web/merch/reports?report=inward-quantity&lot=L%2F1&process=Stitching")
	assert.equal(reportHref("/web/merch/reports", { key: "work_in_progress", value: "work-in-progress" }, context), "/web/merch/reports?report=work-in-progress&lot=L%2F1&item=VEST&process_list=Stitching")
})

test("Summary tab replaces the Lot label and shows the process flow instead of OCR", () => {
	assert.match(source("lotLayout.js"), /tab\.key === "lot" \? \{ \.\.\.tab, label: "Summary" \}/)
	assert.match(source("lotLayout.js"), /\{ key: "lot", label: "Lot" \}/)
	assert.match(source("MerchLotPage.vue"), /<Tab v-for="tab in LOT_VIEW_TABS"/)
	const view = source("LotViewMain.vue")
	assert.match(view, /<LotProcessFlow\b/)
	assert.doesNotMatch(view, /<LotOcrTable\b/)
})

test("cloth lane facts come from the Cloth Program rows", () => {
	const fabric = { program: [
		{ colour: "Red", weight: 356, fabric_split: [{ fabric_type: "Folding Fabric" }] },
		{ colour: "Khaki", weight: 52, fabric_split: [{ fabric_type: "Main Fabric" }] },
		{ colour: "Red", weight: 52, fabric_split: [{ fabric_type: "Main Fabric" }] },
	] }
	assert.deepEqual(fabricSummary(fabric), { programKg: 460, colours: ["Red", "Khaki"], uses: "Folding · Red · Main · Khaki, Red" })
	assert.equal(colourSwatch("Andhra Melange"), "andhramelange")
})

test("report prefill maps the step context to each report's own filter names", () => {
	const context = stepReportContext("L1", "VEST", "Stitching", [{ supplier: "S-1", wo_date: "2026-08-21" }, { supplier: "S-1", wo_date: "2026-08-19" }], "2026-04-02")
	assert.deepEqual(context, { lot: "L1", item: "VEST", process: "Stitching", supplier: "S-1", from_date: "2026-08-19", lot_date: "2026-04-02" })
	const params = (key) => Object.fromEntries(reportPrefill({ key }, context).map((filter) => [filter.param, filter.value]))
	assert.deepEqual(params("work_order"), { lot: "L1", process_name: "Stitching", supplier: "S-1", item: "VEST", based_on: "WO Status" })
	assert.deepEqual(params("size_wise_stock"), { lot: "L1", item: "VEST", process_list: "Stitching" })
	assert.deepEqual(params("multi_ccr"), { lots: "L1", items: "VEST" })
	assert.deepEqual(params("ppo_report"), { items: "VEST" })
	assert.deepEqual(params("dc_report"), { lot: "L1", supplier: "S-1", from_date: "2026-08-19" })
	// Stock and purchase reports: the garment Item and production Supplier would hide every row; dates start at the Lot.
	assert.deepEqual(params("stock_update_report"), { lot: "L1", from_date: "2026-04-02" })
	assert.deepEqual(params("stock_reconciliation_report"), { lot: "L1", from_date: "2026-04-02" })
	assert.deepEqual(params("grn_summary"), { lot: "L1", from_date: "2026-04-02" })
	assert.deepEqual(params("stock_entry_report"), { lot: "L1", item: "VEST", from_date: "2026-04-02" })
	assert.deepEqual(params("supplier_pending"), { supplier: "S-1", process: "Stitching" })
	assert.deepEqual(params("unknown_report"), {})
	assert.equal(stepReportContext("L1", "VEST", "Stitching", [{ supplier: "S-1" }, { supplier: "S-2" }]).supplier, "")
})

test("desk report prefill params are real desk filter fieldnames", async () => {
	const { deskReportConfig } = await import("../src/components/reports/deskReportConfig.js")
	const { REPORT_PREFILL } = await import("../src/utils/lotProcessFlow.js")
	for (const key of ["grn_report", "grn_summary", "dc_report", "stock_entry_report", "stock_reconciliation_report", "stock_update_report"]) {
		const fieldnames = deskReportConfig[key.replaceAll("_", "-")].filters.map((field) => field.fieldname)
		for (const param of Object.values(REPORT_PREFILL[key])) assert.ok(fieldnames.includes(param), `${key}.${param}`)
	}
})

test("every prefilled Vue report reads the same filter names from the URL", () => {
	const reports = {
		"departments/merch/reports/WorkInProgressReport.vue": ["work_in_progress", ["lot", "item", "process_list"]],
		"departments/planning/reports/InwardQuantityReport.vue": ["inward_quantity", ["lot", "process"]],
		"departments/planning/reports/WorkOrderReport.vue": ["work_order", ["lot", "process_name", "supplier", "item", "based_on"]],
		"departments/planning/reports/WorkInProgressReport.vue": ["planning_work_in_progress", ["lot", "item", "process_list"]],
		"departments/planning/reports/SizeWiseStockReport.vue": ["size_wise_stock", ["lot", "item", "process_list"]],
		"departments/planning/reports/WorkOrderPendingReport.vue": ["work_order_pending", ["lot", "item", "process", "supplier"]],
		"departments/planning/reports/ProcessPendingReport.vue": ["process_pending", ["lot", "item", "process"]],
		"departments/planning/reports/ColourWiseDiffReport.vue": ["colour_wise_diff", ["lot", "process_list"]],
		"departments/planning/reports/SupplierPendingReport.vue": ["supplier_pending", ["supplier", "process"]],
		"departments/planning/reports/DispatchPercentageReport.vue": ["dispatch_percentage", ["lot", "item"]],
		"departments/planning/reports/MonthWiseDetailReport.vue": ["month_wise_detail", ["lot", "item"]],
		"departments/finishing/reports/FinishingPlanReport.vue": ["finishing_plan", ["lot", "item"]],
		"departments/cutting/reports/MultiCCRReport.vue": ["multi_ccr", ["lots", "items"]],
		"departments/sales/PpoReport.vue": ["ppo_report", ["items"]],
	}
	return import("../src/utils/lotProcessFlow.js").then(({ REPORT_PREFILL }) => {
		for (const [path, [key, fields]] of Object.entries(reports)) {
			const text = readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
			const call = text.match(/useReportQueryPrefill\(filters, \[([^\]]*)\]/)
			assert.ok(call, path)
			assert.deepEqual(JSON.parse(`[${call[1]}]`), fields, path)
			assert.deepEqual(Object.values(REPORT_PREFILL[key]), fields, key)
		}
	})
})

test("every prefilled filter has a label for the Reports list hint", () => {
	for (const filter of reportPrefill({ key: "work_order" }, { lot: "L1", process: "Cutting", supplier: "S", item: "I" })) assert.ok(filter.label, filter.param)
})

test("Multi CCR opened from a Lot clears its default category", () => {
	const text = readFileSync(new URL("../src/departments/cutting/reports/MultiCCRReport.vue", import.meta.url), "utf8")
	assert.match(text, /useReportQueryPrefill\(filters, \["lots", "items"\], \(\) => \{ filters\.category = ""; generate\(\) \}\)/)
})

test("report search matches name or group, ignoring case and spaces", () => {
	const reports = [
		{ key: "inward_quantity", label: "Inward Quantity" },
		{ key: "inhouse_quantity", label: "In-house Quantity", group: "Production / WIP" },
		{ key: "ppo_report", label: "PPO Report" },
	]
	assert.deepEqual(filterReports(reports, "  QUANT ").map((report) => report.key), ["inward_quantity", "inhouse_quantity"])
	assert.deepEqual(filterReports(reports, "wip").map((report) => report.key), ["inhouse_quantity"])
	assert.deepEqual(filterReports(reports, "ppo").map((report) => report.key), ["ppo_report"])
	assert.deepEqual(filterReports(reports, "zzz"), [])
	assert.equal(filterReports(reports, "").length, 3)
})

test("reports list height fits the larger space around the trigger, within 70% of the viewport", () => {
	assert.equal(reportsListHeight({ top: 600, bottom: 634 }, 700), 490)
	assert.equal(reportsListHeight({ top: 100, bottom: 134 }, 700), 470)
	assert.equal(reportsListHeight({ top: 100, bottom: 134 }, 2000), 1400)
	assert.equal(reportsListHeight({ top: 40, bottom: 74 }, 200), 160)
})

test("both Reports popovers search, bound their height and handle the keyboard", () => {
	for (const workspace of ["merch", "planning"]) {
		const text = readFileSync(new URL(`../src/departments/${workspace}/lot/flow/LotFlowReports.vue`, import.meta.url), "utf8")
		assert.match(text, /filterReports\(props\.reports, query\.value\)/)
		assert.match(text, /reportsListHeight\(trigger\.value\.getBoundingClientRect\(\), window\.innerHeight\)/)
		assert.match(text, /No reports match/)
		for (const key of ["ArrowDown", "Enter", "Escape"]) assert.match(text, new RegExp(`event\\.key === "${key}"`))
		assert.match(text, /event\.stopPropagation\(\)/)
	}
	const css = readFileSync(new URL("../src/styles/lotProcessFlow.css", import.meta.url), "utf8")
	assert.match(css, /\.pf-reports ul \{[^}]*min-height: 0;[^}]*overflow-y: auto;/)
	assert.match(css, /\.pf-reports \{[^}]*flex-direction: column;[^}]*max-height: var\(--pf-reports-height/)
})
