#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	batchPiecesPerBox,
	colourDetails,
	dispatchBySize,
	fillEntry,
	grnBoxQuantities,
	initialEntry,
	packingMode,
	packingRatio,
	ratiosValid,
	coloursValid,
	entryQuantities,
	lotTransferPayload,
	lotTransferErrors,
	dispatchInitialState,
	dispatchEntrySource,
} from "../frontend/src/departments/finishing/finishingEntries.js"
import { ENTRY_DEFINITIONS, entryPayload, missingFields } from "../frontend/src/departments/finishing/finishingEntryDefinitions.js"

const payload = {
	primary_values: ["S", "M"],
	data: { data: {
		Red: { check_value: true, values: { S: { balance: 4, return_qty: 1, pack_return: 0 }, M: { balance: 2, return_qty: 0, pack_return: 3 } } },
		Blue: { check_value: false, values: { S: { balance: 1 }, M: { balance: 0 } } },
	} },
}

const entry = initialEntry(payload)
assert.deepEqual(entry.Red, { checked: true, sizes: { S: 0, M: 0 } })
assert.equal(entry.Blue.checked, false)
fillEntry(payload, entry, "balance")
assert.deepEqual(entry.Red.sizes, { S: 4, M: 2 })
assert.deepEqual(entry.Blue.sizes, { S: 1, M: 0 })
fillEntry(payload, entry, "pack_return")
assert.deepEqual(entry.Red.sizes, { S: 0, M: 3 })
entry.Red.sizes.S = "5"
assert.deepEqual(entryQuantities(entry), { Red: { checked: true, sizes: { S: 5, M: 3 } }, Blue: { checked: false, sizes: { S: 0, M: 0 } } })

const legacy = {}
assert.equal(packingMode(legacy), null)
assert.equal(packingMode({ based_on_other_attribute_mapping: 1, packing_mode: "Size Wise Packing" }), "Size Wise Packing")
assert.equal(packingMode({ based_on_other_attribute_mapping: 0, packing_mode: "Size Ratio Packing" }), null)
const sizes = ["S", "M"]
assert.deepEqual(grnBoxQuantities(null, sizes, { flat: { S: "2", M: "" } }), { S: 2, M: 0 })
assert.deepEqual(grnBoxQuantities("Size Wise Packing", sizes, { colourSize: { Red: { S: 1, M: 2 }, Blue: { S: 3, M: 0 } } }), { S: 4, M: 2 })
const batches = [{ colour: "Red", box_quantity: 2, ratio: { S: 2, M: 3 } }, { colour: "Blue", box_quantity: 1, ratio: { S: 1, M: 4 } }]
assert.deepEqual(grnBoxQuantities("Size Ratio Packing", sizes, { batches }), { S: 5, M: 10 })
assert.equal(batchPiecesPerBox(batches[0], sizes), 5)
assert.equal(ratiosValid(batches, sizes, 5), true)
assert.equal(ratiosValid([{ ratio: { S: 1 } }], sizes, 5), false)
assert.equal(coloursValid(batches, ["Red", "Blue"]), true)
assert.equal(coloursValid([{ colour: "" }], ["Red"]), false)
assert.deepEqual(packingRatio({ packing_size_details: [{ attribute_value: "S", quantity: 2 }, { attribute_value: "M", quantity: 3 }] }), { S: 2, M: 3 })

const config = { packing_combo: 5, packing_size_details: [{ attribute_value: "S", quantity: 2 }, { attribute_value: "M", quantity: 3 }] }
assert.deepEqual(dispatchBySize({ mode: null, sizes, legacy: { S: 1, M: "" } }), { S: 1, M: 0 })
assert.deepEqual(dispatchBySize({ mode: "Size Ratio Packing", sizes, config, colourBoxes: { Red: 5 } }), { S: 2, M: 3 })
assert.deepEqual(dispatchBySize({ mode: "Size Wise Packing", sizes, colourSize: { Red: { S: 1, M: 0 }, Blue: { S: 2, M: 1 } } }), { S: 3, M: 1 })
const available = [{ batch_row: "B1", grn: "GRN-1", colour: "Red", ratio: { S: 2, M: 3 }, available_boxes: 4 }]
assert.deepEqual(dispatchBySize({ dynamic: true, sizes, batches: available, batchBoxes: { B1: 2 } }), { S: 4, M: 6 })
assert.deepEqual(colourDetails({ dynamic: true, sizes, batches: available, batchBoxes: { B1: 2 } }), { Red: { S: 4, M: 6 } })
assert.deepEqual(colourDetails({ mode: "Size Ratio Packing", sizes, config, colourBoxes: { Red: 5, Blue: 0 } }), { Red: { S: 2, M: 3 } })
assert.deepEqual(colourDetails({ mode: "Size Wise Packing", sizes, colourSize: { Red: { S: 1, M: 0 }, Blue: { S: 0, M: 0 } } }), { Red: { S: 1 } })

const rows = [{ source_fp: "FP-2", lot: "L2", warehouse: "W", primary_values: ["S"], old_lot_inward: { data: { Red: { values: { S: { balance_loose_piece: 3, balance_loose_piece_set: 0 } } } } } }]
const transfers = { "FP-2|L2|W": { Red: { set_combination: "Red", sizes: { S: { loose_piece: 2, loose_piece_set: 0 } } } } }
assert.deepEqual(lotTransferPayload(rows, transfers), [{ source_fp: "FP-2", lot: "L2", warehouse: "W", colours: { Red: { set_combination: "Red", sizes: { S: { loose_piece: 2, loose_piece_set: 0 } } } } }])
assert.deepEqual(lotTransferErrors(rows, transfers), [])
transfers["FP-2|L2|W"].Red.sizes.S.loose_piece = 4
assert.match(lotTransferErrors(rows, transfers)[0], /exceeds available \(3\)/)
transfers["FP-2|L2|W"].Red.sizes.S.loose_piece = 1
transfers["FP-2|L2|W"].Red.set_combination = ""
assert.equal(lotTransferErrors(rows, transfers)[0], "Please mention Set Colour")

assert.deepEqual(Object.keys(ENTRY_DEFINITIONS), ["create_delivery_challan", "return_items", "convert_to_loose_piece", "create_grn", "dispatch_box", "add_ironing_excess", "return_pack", "create_alternative_plan", "update_alternative_quantity"])
assert.deepEqual(missingFields(["from_location", "actual_date", "goods_value"], { from_location: "S", actual_date: "", goods_value: 0 }), ["Actual Date"])
assert.deepEqual(missingFields(["goods_value"], { goods_value: null }), ["Goods Value"])
const quantities = { Red: { checked: true, sizes: { S: "2" } } }
assert.deepEqual(entryPayload("create_delivery_challan", { from_location: "S", actual_date: "2026-10-09", selected_type: "return_qty", lot_name: "x" }, quantities), { from_location: "S", actual_date: "2026-10-09", selected_type: "return_qty", quantities: { Red: { checked: true, sizes: { S: 2 } } } })
assert.deepEqual(entryPayload("return_items", { received_type: "Rework" }, quantities), { received_type: "Rework", quantities: { Red: { checked: true, sizes: { S: 2 } } } })
assert.deepEqual(entryPayload("create_grn", { delivery_location: "S", actual_date: "2026-10-09" }, {}, { quantities: { S: 1 }, packing_batches: [] }, "req-1"), { delivery_location: "S", actual_date: "2026-10-09", quantities: { S: 1 }, packing_batches: [], request_id: "req-1" })
assert.deepEqual(entryPayload("create_alternative_plan", { lot_source: "Existing Lot", lot_name: "L", existing_lot: "LOT-9", alternative_item: "ALT", production_detail: "IPD" }, quantities), { lot_source: "Existing Lot", existing_lot: "LOT-9", alternative_item: "ALT", production_detail: "IPD", quantities: { Red: { checked: true, sizes: { S: 2 } } } })

const legacyRow = { values: { S: { qty: 4, dispatch_qty: 2 }, M: { qty: 1, dispatch_qty: 0 } }, total: { total_qty: 5 }, packing_config: {}, batch_dispatches: [], colour_grid: {} }
assert.deepEqual(dispatchInitialState(legacyRow).legacy, { S: 2, M: 0 })
const ratioRow = { values: { S: {}, M: {} }, packing_config: { based_on_other_attribute_mapping: 1, packing_mode: "Size Ratio Packing", colours: ["Red", "Blue"] }, colour_grid: { Red: { S: 0.4, M: 0.6 } } }
assert.deepEqual(dispatchInitialState(ratioRow).colourBoxes, { Red: 1, Blue: 0 })
const wiseRow = { values: { S: {}, M: {} }, packing_config: { based_on_other_attribute_mapping: 1, packing_mode: "Size Wise Packing", colours: ["Red"] }, colour_grid: { Red: { M: 3 } } }
assert.deepEqual(dispatchInitialState(wiseRow).colourSize, { Red: { S: 0, M: 3 } })
assert.deepEqual(dispatchInitialState({ values: {}, batch_dispatches: [{ batch_row: "B1", box_quantity: "2" }] }).batchBoxes, { B1: 2 })
assert.deepEqual(dispatchEntrySource(legacyRow), { sizes: ["S", "M"], packed: { sizes: { S: { packed: 4, dispatched: 0 }, M: { packed: 1, dispatched: 0 } }, total_packed: 5, total_dispatched: 0, dynamic_ratio_packing: false, packing_batches: [] } })

console.log("Finishing entry models: OK")
