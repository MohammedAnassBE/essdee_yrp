import assert from "node:assert/strict"
import test from "node:test"

import * as fabricShapes from "../src/departments/purchase/lot/lotViews.js"

const rows = [
	{
		name: "row-1",
		production_detail: "IPD-1",
		process_name: "Knitting",
		planned_item: "Cloth-26-Greige",
		actual_item: "Cloth-22-Greige",
		actual_quantity: 7,
	},
	{
		name: "row-2",
		production_detail: "IPD-2",
		process_name: "Knitting",
		planned_item: "Cloth-30-Greige",
		actual_item: "Cloth-34-Greige",
		actual_quantity: 0,
	},
	{
		name: "row-3",
		production_detail: "IPD-2",
		process_name: "Knitting",
		planned_item: "Cloth-30-Greige",
		actual_item: "Cloth-30-Greige",
		actual_quantity: 4,
		received_type: "Accepted",
	},
	{
		name: "row-4",
		production_detail: "IPD-2",
		process_name: "Knitting",
		planned_item: "Cloth-30-Greige",
		actual_item: "Cloth-32-Greige",
		actual_quantity: 2,
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
