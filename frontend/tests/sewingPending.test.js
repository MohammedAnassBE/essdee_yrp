import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { gridColumns, gridRows, gridTotals, pendingArgs, pendingGroupLabel } from "../src/departments/sewing/plan/pending.js"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("Pending sends the chosen types and multi-select Lot and Item filters", () => {
	const filters = { fromType: "Line Output", toType: "Checking Output", lots: ["L1", "L2"], items: ["Tee"], workStation: "Line 1" }
	assert.deepEqual(pendingArgs("UNIT", filters), { supplier: "UNIT", from_type: "Line Output", to_type: "Checking Output", lots: ["L1", "L2"], items: ["Tee"], work_station: "Line 1" })
	assert.deepEqual(pendingArgs("UNIT", { lots: [], items: [] }), { supplier: "UNIT", from_type: "", to_type: "", lots: [], items: [], work_station: "" })
})

test("GRN Quantity drops the Work Station filter", () => {
	assert.equal(pendingArgs("UNIT", { fromType: "Line Output", toType: "GRN Quantity", workStation: "Line 1" }).work_station, "")
	assert.equal(pendingArgs("UNIT", { fromType: "GRN Quantity", toType: "Input Qty", workStation: "Line 1" }).work_station, "")
})

test("Pending detail is a colour by size grid with totals", () => {
	const row = { pending: 40, has_part: true, sizes: ["S", "L"], size_totals: { S: 10, L: 30 }, colours: [{ colour: "Red", part: "Top", values: { S: 10, L: 25 }, total: 35 }, { colour: "Blue", part: "Top", values: { L: 5 }, total: 5 }] }
	assert.deepEqual(gridColumns(row).map(column => column.label), ["Colour", "Part", "S", "L", "Total"])
	assert.deepEqual(gridRows(row)[1], { key: "Blue\u0000Top", colour: "Blue", part: "Top", total: 5, "size:S": null, "size:L": 5 })
	assert.deepEqual(gridTotals(row), { total: 40, "size:S": 10, "size:L": 30 })
	assert.deepEqual(gridColumns({ ...row, has_part: false }).map(column => column.key), ["colour", "size:S", "size:L", "total"])
})

test("Pending groups are labelled by Work Station", () => {
	assert.equal(pendingGroupLabel({ work_station: "Line 2" }, true), "Line 2")
	assert.equal(pendingGroupLabel({ work_station: "" }, true), "Not Specified")
	assert.equal(pendingGroupLabel({ work_station: "" }, false), "All Work Stations")
})

test("Sewing Plan workspace mounts the Pending tab", () => {
	const workspace = read("departments/sewing/SewingPlanWorkspace.vue")
	assert.match(workspace, /\{ value: "pending", label: "Pending" \}/)
	assert.match(workspace, /<SewingPending v-else-if="active === 'pending'" :state="pendingState" \/>/)
	assert.match(read("api/sewing.js"), /get_sewing_pending_data/)
	const view = read("departments/sewing/plan/SewingPending.vue")
	assert.match(view, /<LinkMultiSelectField v-model="state.filters.lots" doctype="SD YRP Lot"/)
	assert.match(view, /<LinkMultiSelectField v-model="state.filters.items" doctype="Item"/)
	assert.match(view, /<LinkField v-model="state.filters.workStation" doctype="YRP Work Station"/)
})
