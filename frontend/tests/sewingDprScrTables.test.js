import assert from "node:assert/strict"
import test from "node:test"

import { dprSections, isNegativeBalance, scrColumns, scrLines, scrRows } from "../src/departments/sewing/reports/sewingReportTables.js"

const scr = {
	primary_values: ["S", "M"], headers: ["Order Qty", "Input Qty", "Input Qty Balance"], is_set_item: 1, set_attr: "Part",
	colours: ["Blue", "Red (Blue)"],
	data: {
		Blue: { part: "Top", lines: ["Sewing Line 10"], values: { S: { "Order Qty": 4, "Input Qty": 3, "Input Qty Balance": -1 }, M: { "Order Qty": 6, "Input Qty": 6, "Input Qty Balance": 0 } }, type_wise_total: { "Order Qty": 10, "Input Qty": 9, "Input Qty Balance": -1 } },
		"Red (Blue)": { part: "Bottom", lines: ["Sewing Line 2", "Sewing Line 10"], values: { S: { "Order Qty": 4, "Input Qty": 1, "Input Qty Balance": -3 } }, type_wise_total: { "Order Qty": 4, "Input Qty": 1, "Input Qty Balance": -3 } },
	},
}

test("SCR splits a set item part-wise under each Type, with a row Total", () => {
	const rows = scrRows(scr)
	assert.deepEqual(rows.map(row => [row.type, row.colour, row.part, row.total]), [
		["Order Qty", "Blue", "Top", 10], ["Order Qty", "Red (Blue)", "Bottom", 4],
		["Input Qty", "Blue", "Top", 9], ["Input Qty", "Red (Blue)", "Bottom", 1],
		["Input Qty Balance", "Blue", "Top", -1], ["Input Qty Balance", "Red (Blue)", "Bottom", -3],
	])
	assert.equal(rows[3]["size:M"], 0)
	assert.deepEqual(scrColumns(scr).map(column => column.label), ["Colour", "Part", "Type", "S", "M", "Total"])
	assert.deepEqual(scrColumns({ ...scr, is_set_item: 0 }).map(column => column.label), ["Colour", "Type", "S", "M", "Total"])
})

test("SCR colour filter, line order and negative balances follow production_api", () => {
	assert.deepEqual(scrRows(scr, ["Red (Blue)"]).map(row => row.colour), ["Red (Blue)", "Red (Blue)", "Red (Blue)"])
	assert.deepEqual(scrLines(scr), ["Sewing Line 2", "Sewing Line 10"])
	assert.equal(isNegativeBalance("Input Qty Balance", -1), true)
	assert.equal(isNegativeBalance("Delivered - Input", -2), true)
	assert.equal(isNegativeBalance("Input Qty", -1), false)
})

test("DPR has one section per Input Type with its Total Qty and per-Lot tables", () => {
	const reports = [{
		date: "2026-07-10", headers: ["Input Qty", "Line Output", "AQL Output"],
		dpr_data: {
			"Line Output": {
				L1: { item: "Set", is_set_item: 1, set_attr: "Part", primary_values: ["S"], details: { "Sewing Line 1": { Accepted: {
					"Blue@1": { colour: "Blue@1", part: "Top", values: { S: 5 }, total: 5 },
					"Red (Blue)": { colour: "Red (Blue)", part: "Bottom", values: { S: 3 }, total: 3 },
				} } } },
				L2: { item: "Tee", is_set_item: 0, primary_values: ["S", "M"], details: { "Sewing Line 2": { Accepted: { Green: { colour: "Green", part: null, values: { M: 4 }, total: 4 } } } } },
			},
			"Input Qty": { L1: { item: "Set", is_set_item: 1, set_attr: "Part", primary_values: ["S"], details: { "Sewing Line 1": { Accepted: { Blue: { colour: "Blue", part: "Top", values: { S: 7 }, total: 7 } } } } } },
		},
	}]
	const sections = dprSections(reports)
	assert.deepEqual(sections.map(section => [section.stage, section.total]), [["Input Qty", 7], ["Line Output", 12]])
	const [setTable, plainTable] = sections[1].tables
	assert.deepEqual(setTable.columns.map(column => column.label), ["#", "Lot", "Item", "Colour", "Line", "Type", "Part", "S", "Remarks", "Total"])
	assert.deepEqual(plainTable.columns.map(column => column.label), ["#", "Lot", "Item", "Colour", "Line", "Type", "S", "M", "Remarks", "Total"])
	assert.deepEqual(setTable.rows.map(row => [row.index, row.colour, row.part, row["size:S"], row.total]), [[1, "Blue", "Top", 5, 5], [2, "Red (Blue)", "Bottom", 3, 3]])
	assert.equal(plainTable.rows[0]["size:S"], undefined)
})
