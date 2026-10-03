import assert from "node:assert/strict"
import test from "node:test"

import {
	addGrnActualDia,
	addGrnReceivedType,
	buildGrnLogicalRows,
	compactGrnRouteSplits,
	setGrnSplitQuantity,
} from "../src/engine/stock/grnRouteRows.js"
import * as grnRoutes from "../src/engine/stock/grnRouteRows.js"

const routeEntry = (qty, reference) => ({
	name: "Dyed Fabric 36's RL",
	attributes: { Dia: "26 Dia", Colour: "Greige" },
	dimensions: { lot: "LOT-1", received_type: "Accepted" },
	primary_attribute: "",
	default_uom: "Kg",
	values: {
		default: {
			qty,
			pending_quantity: qty,
			max_receivable_quantity: qty,
			ref_doctype: "Work Order Receivables",
			ref_docname: reference,
		},
	},
})

const grouped = (entries) => [{
	attributes: ["Dia", "Colour"],
	primary_attribute: "",
	primary_attribute_values: [],
	items: entries,
}]

test("combines identical physical GRN routes and keeps every source reference", () => {
	const source = grouped([
		routeEntry(3.774, "WOR-1"),
		routeEntry(3.774, "WOR-2"),
		routeEntry(3.384, "WOR-3"),
		routeEntry(4.295, "WOR-4"),
		routeEntry(3.773, "WOR-5"),
	])
	const rows = buildGrnLogicalRows(source)

	assert.equal(rows.length, 1)
	assert.equal(rows[0].splits.length, 1)
	assert.equal(rows[0].splits[0].entry.values.default.qty, 19)
	assert.equal(rows[0].splits[0].entry.values.default.pending_quantity, 19)
	assert.equal(rows[0].splits[0].entry.values.default.max_receivable_quantity, 19)
	assert.deepEqual(
		rows[0].splits[0].sourceEntries.map((entry) => entry.values.default.ref_docname),
		["WOR-1", "WOR-2", "WOR-3", "WOR-4", "WOR-5"],
	)

	setGrnSplitQuantity(rows[0].splits[0], "default", 10)
	assert.equal(
		source[0].items.reduce((sum, entry) => sum + entry.values.default.qty, 0),
		10,
	)
})

test("adding an Actual Dia creates one physical receipt row", () => {
	const source = grouped([
		routeEntry(9, "WOR-1"),
		routeEntry(10, "WOR-2"),
	])
	const row = buildGrnLogicalRows(source)[0]

	addGrnActualDia(source, row, "22 Dia")

	const added = source[0].items.filter((entry) => entry.attributes.Dia === "22 Dia")
	assert.equal(added.length, 1)
	assert.deepEqual(
		added.map((entry) => entry.values.default.ref_docname),
		["WOR-1"],
	)
	assert.deepEqual(added.map((entry) => entry.values.default.qty), [0])
})

test("initial split compaction stores one zero-quantity physical default row", () => {
	const accepted = [
		routeEntry(0, "WOR-1"),
		routeEntry(0, "WOR-2"),
		routeEntry(0, "WOR-3"),
	]
	const rejected = accepted.map((entry) => ({
		...structuredClone(entry),
		dimensions: { ...entry.dimensions, received_type: "Rejected" },
	}))
	const source = grouped([...accepted, ...rejected])

	const compacted = compactGrnRouteSplits(source, "Accepted")

	assert.equal(compacted[0].items.length, 1)
	assert.deepEqual(
		compacted[0].items.map((entry) => entry.values.default.ref_docname),
		["WOR-1"],
	)
})

test("Received Type split creates one physical row instead of every hidden route", () => {
	const source = grouped([
		routeEntry(40, "WOR-1"),
		routeEntry(60, "WOR-2"),
	])
	const row = buildGrnLogicalRows(source)[0]

	addGrnReceivedType(source, row, "Rejected")

	const rejected = source[0].items.filter(
		(entry) => entry.dimensions.received_type === "Rejected",
	)
	assert.equal(rejected.length, 1)
	assert.equal(rejected[0].values.default.qty, 0)
})

test("physical receipt quantity is not capped or distributed across hidden routes", () => {
	const source = compactGrnRouteSplits(grouped([
		routeEntry(40, "WOR-1"),
		routeEntry(60, "WOR-2"),
	]), "Accepted")
	const split = buildGrnLogicalRows(source)[0].splits[0]

	setGrnSplitQuantity(split, "default", 110)

	assert.equal(source[0].items.length, 1)
	assert.equal(source[0].items[0].values.default.qty, 110)
})

test("standard fabric GRN accepts an actual receipt above the Work Order allowance", () => {
	assert.equal(typeof grnRoutes.normalizeGrnReceiptQuantity, "function")
	assert.equal(grnRoutes.normalizeGrnReceiptQuantity(110, 100, 0, true), 110)
	assert.equal(grnRoutes.normalizeGrnReceiptQuantity(110, 100, 0, false), 100)
})
