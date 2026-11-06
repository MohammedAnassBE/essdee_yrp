import test from "node:test"
import assert from "node:assert/strict"

import {
	groupLotsByPpo,
	hasTrackingScope,
	hiddenDispatchNote,
	matchingTrackingLots,
	ppoFigures,
	processMeasure,
	progressStrip,
	pruneTrackingFilters,
	trackingCsv,
	trackingFilterOptions,
	trackingSummary,
} from "../src/departments/planning/dashboard/trackingRows.js"

const process = (name, kind, status, values = {}) => ({ name, kind, status, first_dc: "2026-08-01", planned: 100, delivered: 100, received: 90, dispatch: 0, reason: "WO Closed", work_orders: [{ name: `WO-${name}`, supplier: "S1", status: "Closed" }], ...values })
const lots = [
	{ lot: "L-1", ppo: "PPO-1", item: "A", delivery: "2026-06-15", qty: 1000, status: "Packing in progress", planned: 1000, cut: 1100, cut_pcs: 1100, total: 1100, dispatch: 900, balance: 200,
		processes: [process("Cutting", "cutting", "partial", { planned: 1200, received: 1100 }), process("Stitching", "item", "done"), process("Packing", "packing", "partial", { received: 950, dispatch: 900 })] },
	{ lot: "L-2", ppo: "PPO-1", item: "A", delivery: "2026-06-15", qty: 500, status: "Dispatched", planned: 500, cut: 520, cut_pcs: 520, total: 520, dispatch: 500, balance: 20,
		processes: [process("Cutting", "cutting", "done"), process("Packing", "packing", "done")] },
	{ lot: "L-3", ppo: "PPO-2", item: "B", delivery: "2026-10-05", qty: 300, status: "Fabric not received", planned: 300, cut: 0, cut_pcs: 0, total: 300, dispatch: 0, balance: 300,
		processes: [process("Knitting", "cloth", "idle", { first_dc: null, planned: 50, delivered: 0, received: 0 })] },
]
const ppos = {
	"PPO-1": { item: "A", item_name: "Alpha", boxes: 150, pieces_per_box: 10, pieces: 1500, lots: [{ lot: "L-1", has_work_order: true, planned: 1000 }, { lot: "L-2", has_work_order: true, planned: 500 }, { lot: "L-9", has_work_order: false, planned: 400 }],
		work_order_lots: [{ lot: "L-1", status: "Packing in progress", qty: 1000, cut_pcs: 1100, dispatch: 900 }, { lot: "L-2", status: "Dispatched", qty: 500, cut_pcs: 520, dispatch: 500 }] },
	"PPO-2": { item: "B", item_name: "Beta", boxes: 30, pieces_per_box: null, pieces: null, lots: [{ lot: "L-3", has_work_order: true, planned: 300 }], work_order_lots: [{ lot: "L-3", status: "Fabric not received", qty: 300, cut_pcs: 0, dispatch: 0 }] },
}
const data = { as_of: "2026-11-06", ppos, lots }

test("Process filter keeps only those processes and drops lots without them", () => {
	const matching = matchingTrackingLots(lots, { ppo: ["PPO-1"], lot: [], process: ["Stitching"] })
	assert.deepEqual(matching.map((row) => [row.lot, row.processes.length]), [["L-1", 1]])
	assert.equal(hasTrackingScope({ ppo: [], lot: [], process: ["Cutting"] }), false)
	assert.equal(hasTrackingScope({ ppo: [], lot: ["L-1"], process: [] }), true)
})

test("summary ignores the Process filter and counts not-started lots of selected PPOs", () => {
	const summary = trackingSummary(data, { ppo: ["PPO-1", "PPO-2"], lot: [], process: ["Stitching"] })
	assert.deepEqual([summary.ppoCount, summary.lotCount, summary.openLots, summary.dispatchedLots, summary.notStartedLots], [2, 4, 2, 1, 1])
	assert.deepEqual([summary.ppoBoxes, summary.ppoPieces, summary.dispatched, summary.workInProgress, summary.notStarted], [180, 1500, 1400, 500, 400])
	const lotsOnly = trackingSummary({ ...data, lots: [lots[0]] }, { ppo: [], lot: ["L-1"], process: [] })
	assert.deepEqual([lotsOnly.ppoCount, lotsOnly.lotCount, lotsOnly.notStarted, lotsOnly.isLotsOnly], [1, 1, 0, true])
})

test("PPO figures cover every lot of the PPO and flag Cut over PPO", () => {
	const figures = ppoFigures(ppos["PPO-1"])
	assert.deepEqual([figures.lotPieces, figures.cut, figures.dispatch, figures.balance, figures.isCutOver], [1500, 1620, 1400, 100, true])
	assert.equal(ppoFigures(ppos["PPO-2"]).balance, null)
})

test("hidden-dispatch note offers show only when the hidden lots are dispatched", () => {
	const note = hiddenDispatchNote(ppos["PPO-1"], [lots[0]], false)
	assert.deepEqual(note, { count: 1, pieces: 500, canShow: true })
	assert.equal(hiddenDispatchNote(ppos["PPO-1"], [lots[0], lots[1]], true), null)
})

test("measure uses lot order pcs for packing and Kg for cloth", () => {
	assert.equal(processMeasure(lots[0], lots[0].processes[2]).percent, 95)
	assert.equal(processMeasure(lots[0], lots[0].processes[1]).percent, 90)
	assert.equal(processMeasure(lots[2], lots[2].processes[0]).isCloth, true)
})

test("progress strip counts done processes and names the latest with activity", () => {
	const strip = progressStrip(lots[0])
	assert.deepEqual([strip.done, strip.total, strip.current, strip.segments.map((segment) => segment.status).join()], [1, 3, "Packing", "partial,done,partial"])
	assert.equal(progressStrip(lots[2]).current, "Not started")
})

test("options narrow lots by PPO and processes by scope; pruning drops stale picks", () => {
	const options = { ppos: [{ name: "PPO-1", item: "A", item_name: "Alpha" }, { name: "PPO-2", item: "B", item_name: "B" }], lots: [{ name: "L-1", item: "A", ppo: "PPO-1" }, { name: "L-3", item: "B", ppo: "PPO-2" }] }
	const result = trackingFilterOptions(options, lots, { ppo: ["PPO-1"], lot: [], process: [] })
	assert.deepEqual(result.ppo.map((option) => option.hint), ["A · Alpha", "B"])
	assert.deepEqual(result.lot.map((option) => option.value), ["L-1"])
	assert.deepEqual(result.process.map((option) => [option.value, option.hint]), [["Cutting", "2 lots"], ["Stitching", "1 lot"], ["Packing", "2 lots"]])
	assert.deepEqual(pruneTrackingFilters({ ppo: ["PPO-1"], lot: ["L-1", "L-3"], process: ["Knitting", "Packing"] }, result), { ppo: ["PPO-1"], lot: ["L-1"], process: ["Packing"] })
})

test("lots group under their PPO in order", () => {
	assert.deepEqual(groupLotsByPpo(lots).map(([ppo, rows]) => [ppo, rows.length]), [["PPO-1", 2], ["PPO-2", 1]])
})

test("CSV has the PPO and lot figures then each visible process", () => {
	const lines = trackingCsv([lots[0], lots[2]], ppos).split("\n")
	assert.equal(lines[0], "PPO,PPO Qty boxes,PPO pcs,PPO Cut pcs,PPO Dispatch pcs,PPO Balance pcs,Lot,Item,Status,Delivery,Lot pcs,Cut pcs,Dispatch pcs,Balance pcs,Cutting Delivered Kg,Cutting Received pcs,Stitching Delivered pcs,Stitching Received pcs,Packing Delivered pcs,Packing Received pcs,Knitting Delivered Kg,Knitting Received Kg")
	assert.equal(lines[1].split(",").slice(0, 14).join(","), "PPO-1,150,1500,1620,1400,100,L-1,A,Packing in progress,15-06-2026,1000,1100,900,200")
	assert.equal(lines[2].split(",").slice(-6).join(","), ",,,,0,0")
})

test("trackingSummary counts only selected PPOs the server returned", () => {
	const data = { ppos: { "PPO-1": { boxes: 1, pieces: 10, lots: [] } }, lots: [] }
	assert.equal(trackingSummary(data, { ppo: ["PPO-1", "PPO-DRAFT"], lot: [], process: [] }).ppoCount, 1)
})
