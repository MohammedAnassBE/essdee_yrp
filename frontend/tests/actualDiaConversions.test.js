import assert from "node:assert/strict"
import test from "node:test"

import { conversionProcesses, conversionView } from "../src/departments/purchase/lot/lotViews.js"

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

test("actual Dia Lot view shows changed routes regardless of quantity or receipt type", () => {
	const view = conversionView(rows)

	assert.equal(view.changed, 3)
	assert.equal(view.routes, 4)
	assert.deepEqual(conversionProcesses(rows), ["Knitting"])
	assert.deepEqual(view.rows.map((row) => row.name), ["row-1", "row-2", "row-4"])
})

test("actual Dia Lot view filters by process, search and unchanged visibility", () => {
	const view = conversionView(rows, {
		process: "Knitting",
		search: "30-greige",
		includeUnchanged: true,
	})

	assert.deepEqual(view.rows.map((row) => row.name), ["row-2", "row-3", "row-4"])
	assert.equal(view.changed, 3)
	assert.equal(view.routes, 4)
	assert.deepEqual(conversionView(rows, { search: "22-GREIGE" }).rows.map((row) => row.name), ["row-1"])
	assert.deepEqual(conversionView(rows, { process: "Dyeing", includeUnchanged: true }).rows, [])
})
