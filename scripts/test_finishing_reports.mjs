#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	FROZEN_COLUMNS,
	dispatchDiff,
	dispatchTotals,
	firstColourLabel,
	formatReportCell,
	frozenColumnOffsets,
	groupByDate,
	ironingShowsPart,
	normalizeReportColumn,
	packedTotals,
	reportCellTone,
	sumBy,
} from "../frontend/src/departments/finishing/reports/finishingReports.js"

const packed = [{ date: "2026-10-02", lot: "L1", total_pieces: 10, total_boxes: 2 }, { date: "2026-10-01", lot: "L2", total_pieces: 5, total_boxes: 1 }, { date: "2026-10-02", lot: "L3", total_pieces: 1.5, total_boxes: 0 }]
assert.deepEqual(packedTotals(packed), { pieces: 16.5, boxes: 3 })
assert.deepEqual(groupByDate(packed).map((group) => [group.date, group.rows.length]), [["2026-10-02", 2], ["2026-10-01", 1]])
assert.equal(sumBy(packed, "total_pieces"), 16.5)

const dispatch = [{ packed_total_boxes: 10, packed_total_pieces: 50, dispatched_total_boxes: 4, dispatched_total_pieces: 20 }, { packed_total_boxes: 0, packed_total_pieces: 0, dispatched_total_boxes: 2, dispatched_total_pieces: 10 }]
assert.deepEqual(dispatchTotals(dispatch), { packedBoxes: 10, packedPieces: 50, dispatchedBoxes: 6, dispatchedPieces: 30, diffBoxes: 4, diffPieces: 20 })
assert.equal(dispatchDiff(5, 5), "")
assert.equal(dispatchDiff(5, undefined), 5)
assert.equal(dispatchDiff(undefined, 2), -2)

assert.equal(ironingShowsPart({ attributes: ["Colour", "Part"], rows: [{ part: "Top" }] }), true)
assert.equal(ironingShowsPart({ attributes: ["Colour", "Part"], rows: [{ part: "" }] }), false)
assert.equal(ironingShowsPart({ attributes: ["Colour"], rows: [{ part: "Top" }] }), false)

assert.deepEqual(normalizeReportColumn("Lot Name:Link/SD YRP Lot:120"), { label: "Lot Name", fieldname: "lot_name", fieldtype: "Link", options: "SD YRP Lot", width: 120, align: "auto" })
assert.deepEqual(normalizeReportColumn({ label: "Cut Qty", fieldname: "cutting", fieldtype: "Int", width: 96, align: "center" }), { label: "Cut Qty", fieldname: "cutting", fieldtype: "Int", options: "", width: 96, align: "center" })
assert.equal(formatReportCell({ fieldname: "p", fieldtype: "Percent" }, { p: 12.345 }), "12.35%")
assert.equal(formatReportCell({ fieldname: "q", fieldtype: "Int" }, { q: 12820 }), "12,820")
assert.equal(formatReportCell({ fieldname: "q", fieldtype: "Int" }, { q: 0 }), "0")
assert.equal(formatReportCell({ fieldname: "q", fieldtype: "Float" }, { q: 1.5 }), "1.5")
assert.equal(formatReportCell({ fieldname: "q", fieldtype: "Data" }, { q: null }), "")
assert.equal(reportCellTone({ fieldname: "sewing_diff" }, { sewing_diff: -3 }), "negative")
assert.equal(reportCellTone({ fieldname: "unaccountable" }, { unaccountable: 2 }), "positive")
assert.equal(reportCellTone({ fieldname: "unaccountable" }, { unaccountable: 0 }), "")
assert.equal(reportCellTone({ fieldname: "cutting" }, { cutting: -3 }), "")
assert.deepEqual(FROZEN_COLUMNS, ["item", "description", "lot", "pieces_per_box"])
assert.deepEqual(frozenColumnOffsets([
	{ key: "base:item", kind: "base", fieldname: "item" },
	{ key: "linked:lot:item", kind: "linked", fieldname: "item" },
	{ key: "base:description", kind: "base", fieldname: "description" },
], [120, 200, 160]), {
	"base:item": 0,
	"base:description": 120,
})

assert.equal(firstColourLabel({ "Oil Mark-Red-Top": {} }), "Red-Top")
assert.equal(firstColourLabel({}), "")

console.log("Finishing report helpers: OK")
