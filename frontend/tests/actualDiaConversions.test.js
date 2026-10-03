import assert from "node:assert/strict"
import test from "node:test"

import * as fabricShapes from "../src/views/fabric/fabricShapes.js"

const rows = [
	{
		name: "row-1",
		production_detail: "IPD-1",
		process_name: "Knitting",
		from_item: "Cloth-26-Greige",
		to_item: "Cloth-22-Greige",
		to_qty: 7,
	},
	{
		name: "row-2",
		production_detail: "IPD-2",
		process_name: "Knitting",
		from_item: "Cloth-30-Greige",
		to_item: "Cloth-34-Greige",
		to_qty: 0,
	},
	{
		name: "row-3",
		production_detail: "IPD-2",
		process_name: "Knitting",
		from_item: "Cloth-30-Greige",
		to_item: "Cloth-30-Greige",
		to_qty: 4,
		received_type: "Accepted",
	},
	{
		name: "row-4",
		production_detail: "IPD-2",
		process_name: "Knitting",
		from_item: "Cloth-30-Greige",
		to_item: "Cloth-32-Greige",
		to_qty: 2,
		received_type: "Rejected",
	},
]

test("actual Dia Lot view shows only positive Accepted physical conversions", () => {
	assert.equal(typeof fabricShapes.buildActualDiaConversionView, "function")
	const view = fabricShapes.buildActualDiaConversionView(rows)

	assert.equal(view.changedCount, 1)
	assert.deepEqual(view.processes, ["Knitting"])
	assert.deepEqual(view.filteredRows.map((row) => row.name), ["row-1"])
	assert.deepEqual(view.groups.map((group) => group.productionDetail), ["IPD-1"])
})

test("actual Dia Lot view filters by process, search and unchanged visibility", () => {
	assert.equal(typeof fabricShapes.buildActualDiaConversionView, "function")
	const view = fabricShapes.buildActualDiaConversionView(rows, {
		process: "Knitting",
		search: "30-greige",
		includeUnchanged: true,
	})

	assert.deepEqual(view.filteredRows.map((row) => row.name), ["row-3"])
	assert.deepEqual(view.groups.map((group) => group.productionDetail), ["IPD-2"])
})
