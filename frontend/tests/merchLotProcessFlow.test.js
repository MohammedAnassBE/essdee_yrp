import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import {
	clothHeadline, colourSwatch, diffTone, fabricSummary, itemHeadline, percent, reportHref, sizeTable, statusTone, workOrderHref,
} from "../src/departments/merch/lot/flow/processFlow.js"

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
	assert.equal(reportHref({ key: "inhouse_quantity", value: "inhouse-quantity" }, "L/1", "Ironing and Packing"), "/web/merch/reports?report=inhouse-quantity&lot=L%2F1&process=Ironing+and+Packing")
	assert.equal(reportHref({ key: "work_order", value: "work-order" }, "L1", "Cutting"), "/web/merch/reports?report=work-order")
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
