#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	colourLabel,
	detailsMatrix,
	differenceTone,
	inwardMatrix,
	ocrModel,
	packedRows,
	percentage,
	quantityMatrix,
	reworkMatrix,
	singleMetricMatrix,
} from "../frontend/src/departments/finishing/finishingViews.js"

const sizes = ["S", "M"]
const cells = (row) => row.cells.map((cell) => cell.value)
const tones = (row) => row.cells.map((cell) => cell.tone)

assert.equal(differenceTone(-1), "negative")
assert.equal(differenceTone(2), "positive")
assert.equal(differenceTone(0), "zero")
assert.equal(differenceTone(0, "zero-inward"), "zero-inward")
assert.equal(colourLabel("Red (Red) @ Top"), "Red (Red)")
assert.equal(colourLabel("Blue"), "Blue")

const detailValues = (cutting, delivered, received) => ({ cutting, delivered, received, cut_sew_diff: delivered - cutting, difference: received - delivered })
const details = detailsMatrix({
	primary_values: sizes,
	process: "Stitching",
	is_set_item: 0,
	data: {
		data: { "Red@x": { part: null, values: { S: detailValues(10, 8, 9), M: detailValues(5, 5, 5) }, colour_total: { cutting: 15, delivered: 13, received: 14, cut_sew_diff: -2, difference: 1 } } },
		total: { item: { S: detailValues(10, 8, 9), M: detailValues(5, 5, 5) } },
		over_all: { item: { cutting: 15, delivered: 13, received: 14, cut_sew_diff: -2, difference: 1 } },
	},
})
assert.deepEqual(details.groups[0].rows.map((row) => row.label), ["Cutting Qty", "Stitching Delivered", "Difference", "Stitching Delivered", "Stitching Received", "Difference"])
assert.equal(details.groups[0].colour, "Red")
assert.deepEqual(cells(details.groups[0].rows[2]), [-2, 0])
assert.deepEqual(tones(details.groups[0].rows[2]), ["negative", "zero"])
assert.equal(details.groups[0].rows[2].total.tone, "negative")
assert.deepEqual(tones(details.groups[0].rows[5]), ["positive", "zero"])
assert.equal(details.groups[0].rows[0].tone, undefined)
assert.equal(details.groups[1].total, true)
assert.equal(details.groups[1].colour, "Total")
assert.equal(details.groups[1].rows[0].total.value, 15)

const quantity = quantityMatrix({
	primary_values: sizes,
	data: { data: { Red: { values: { S: { accepted: 4, dc_qty: 3, balance: 1, return_qty: 0, pack_return: 0 } }, colour_total: { accepted: 4 } } } },
	rework_details: { data: { Red: { values: { S: { rework_qty: 2, reworked: 1, pending: 1, rejected: 0 } }, colour_total: { rework_qty: 2 } } } },
})
assert.deepEqual(quantity.groups[0].rows.map((row) => row.label), ["Accepted", "Delivered", "Balance", "Loose Piece", "Loose Piece Packed"])
assert.deepEqual(cells(quantity.groups[0].rows[0]), [4, 0])
const rework = reworkMatrix({ primary_values: sizes, rework_details: quantity.source.rework_details })
assert.deepEqual(rework.groups[0].rows.map((row) => row.label), ["Rework Quantity", "Reworked", "Pending", "Rejected"])
assert.deepEqual(cells(rework.groups[0].rows[2]), [1, 0])

const inward = inwardMatrix({ primary_values: sizes, data: { data: { Red: { values: { S: { accepted: 1, reworked: 0, rejected: 0, pending: 0 }, M: { pending: -3 } }, colour_total: { pending: -3 } } } } })
assert.deepEqual(tones(inward.groups[0].rows[3]), ["zero-inward", "negative"])
assert.equal(inward.groups[0].rows[3].total.tone, "negative")

const ironing = singleMetricMatrix({ primary_values: sizes, data: { data: { Red: { values: { S: { ironing: 2 }, M: { ironing: 1 } }, colour_total: { ironing: 3 } } }, total: { S: { ironing: 2 }, M: { ironing: 1 } }, total_qty: { ironing: 3 } } }, "ironing")
assert.deepEqual(cells(ironing.groups[0].rows[0]), [2, 1])
assert.deepEqual(cells(ironing.groups[1].rows[0]), [2, 1])
assert.equal(ironing.groups[1].rows[0].total.value, 3)
const packReturn = singleMetricMatrix({ primary_values: sizes, data: { data: { Red: { values: { S: { pack_returned_qty: 4 } }, colour_total: 4 } }, total: { S: 4, M: 0 }, total_qty: 4 } }, "pack_returned_qty")
assert.equal(packReturn.groups[0].rows[0].total.value, 4)
assert.deepEqual(cells(packReturn.groups[1].rows[0]), [4, 0])

const packed = packedRows({ primary_values: sizes, packed: { sizes: { S: { packed: 10, dispatched: 4 } }, total_packed: 10, total_dispatched: 4 } })
assert.deepEqual(packed.map((row) => row.label), ["Packed", "Dispatched", "Balance"])
assert.deepEqual(packed[2].cells, [6, 0])
assert.equal(packed[2].total, 6)
assert.equal(packedRows({ primary_values: sizes, packed: { sizes: {}, dynamic_ratio_packing: true } })[0].label, "Packed Pieces")

assert.equal(percentage(50, 25), 50)
assert.equal(percentage(0, 25), 0)
assert.equal(percentage(100, -12.345, true), 12.35)

const sizeTotals = { cutting_qty: 100, sewing_received: 98, old_lot: 2, ironing_excess: 1, total_inward: 101, dc_qty: 95, transferred: 1, transferred_as_loose_piece: 0, packed_box: 19, packed_box_qty: 95, dispatched_box: 19, dispatched_piece: 95, order_qty: 100, rejected: 2, loose_piece: 1, loose_piece_set: 0, pending: 1 }
const part = {
	data: { Red: { values: { S: { rejected: 2, loose_piece: 1, loose_piece_set: 0, pending: 1 } }, colour_total: { rejected: 2, loose_piece: 1, loose_piece_set: 0, pending: 1 } } },
	total: { S: sizeTotals },
	cutting: 100, sewing_received: 98, old_lot: 2, ironing_excess: 1, total_inward: 101, dc_qty: 95, transferred: 1, transferred_as_loose_piece: 0, packed_box: 19, packed_box_qty: 95, dispatched_box: 19, dispatched_piece: 95, order_qty: 100, rejected: 2, loose_piece: 1, loose_piece_set: 0, pending: 1,
}
const ocr = ocrModel(part, ["S"])
const summary = Object.fromEntries(ocr.summary.map((row) => [row.label, row]))
assert.equal(summary["Difference ( A - B )"].total.value, -2)
assert.equal(summary["Difference ( A - B )"].total.tone, "negative")
assert.equal(summary["Difference ( (E + F) - D )"].total.value, -5)
assert.equal(summary["Order to Dispatch Diff ( O - H )"].total.value, 5)
assert.equal(ocr.unaccountable.total.value, -1)
assert.deepEqual(ocr.breakdowns.map((section) => section.label), ["Rejection Pieces ( I )", "Loose Piece ( J )", "Loose Piece Set ( K )", "Rework Pieces ( L )"])
assert.equal(ocr.breakdowns[2].rows[0].cells[0].value, null)
const percentages = Object.fromEntries(ocr.percentages.map((row) => [row.label, row]))
assert.equal(percentages["Cut to Dispatch"].value, 93.14)
assert.equal(percentages["Cut to Dispatch"].difference, "6.86")
assert.equal(percentages["Cut to Inward"].value, 98)
assert.equal(percentages["Finishing Not Received"].value, 1.94)
assert.equal(percentages["OCR Complete"].value, "98.96")
assert.equal(percentages.Unaccountable.value, "-0.97")
assert.equal(percentages.Rejection.difference, "")

console.log("Finishing view models: OK")
