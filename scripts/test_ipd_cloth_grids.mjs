#!/usr/bin/env node
import assert from "node:assert/strict"

import {
	addCompactingTargets,
	applyProcessEdit,
	compactingInputDias,
	compactingRoutePairs,
	compactingTargets,
	fillCompactingDia,
	modelToRows,
	newMappingRow,
	newProcessRow,
	nextSequence,
	orphanMappingCount,
	pairColours,
	ratioTotal,
	removeProcess,
	removeRow,
	rowKey,
	rowsToModel,
	sortBySequence,
	withStoredOptions,
} from "../frontend/src/departments/merch/ipd/cloth/clothGrids.js"

const ATTRIBUTES = { colourAttribute: "Colour", diaAttribute: "Dia" }

function testRowModelRoundTrip() {
	const rows = [{ name: "a", yarn_item: "Yarn 40", ratio: 58 }, { yarn_item: "Poly", ratio: 42 }]
	const model = rowsToModel(rows, ["yarn_item", "ratio"])
	assert.deepEqual(Object.keys(model), ["a", "new:1"])
	assert.deepEqual(modelToRows(rows, model, ["yarn_item", "ratio"]), rows)
	const edited = modelToRows(rows, { ...model, a: { ...model.a, ratio: 60 } }, ["yarn_item", "ratio"])
	assert.deepEqual(edited[0], { name: "a", yarn_item: "Yarn 40", ratio: 60 })
	assert.equal(edited[1], rows[1])
	assert.equal(modelToRows([{ name: "x" }], { x: { ratio: null } }, ["ratio"])[0].ratio, undefined)
	assert.deepEqual(removeRow(rows, "new:1"), [rows[0]])
	assert.equal(rowKey({}, 4), "new:4")
}

function testRatioTotal() {
	assert.equal(ratioTotal([{ ratio: 58 }, { ratio: 42 }]), 100)
	assert.equal(ratioTotal([{ ratio: 33.333 }, { ratio: 33.333 }, { ratio: 33.334 }]), 100)
	assert.equal(ratioTotal([{ ratio: null }, { ratio: "10" }]), 10)
}

function testProcessRows() {
	const processes = [{ name: "p1", sequence: 10, output_item: "Fabric" }, { name: "p2", sequence: 20, output_item: "Fabric" }]
	assert.equal(nextSequence(processes), 30)
	assert.equal(nextSequence([]), 10)
	assert.deepEqual(newProcessRow(processes, { item: "Fabric", defaultInput: "Yarn" }), { sequence: 30, fabric_process: null, input_item: "Fabric", output_item: "Fabric", quantity_ratio: 1 })
	assert.equal(newProcessRow([], { item: "Fabric", defaultInput: "Yarn" }).input_item, "Yarn")
	const mappings = [{ name: "m1", sequence: 10, mapping_index: 0 }, { name: "m2", sequence: 20, mapping_index: 0 }, { name: "m3", sequence: 20, mapping_index: 1 }]
	assert.deepEqual(newMappingRow(processes, mappings), { sequence: 20, mapping_index: 2, attribute: null, role: "Change", from_value: null, to_value: null })
	assert.equal(newMappingRow(processes, []).mapping_index, 0)
	return { processes, mappings }
}

function testProcessSequenceEdit() {
	const { processes, mappings } = testProcessRows()
	const unchanged = applyProcessEdit(processes, mappings, processes.map((row) => ({ ...row })))
	assert.equal(unchanged.mappings, mappings)
	assert.deepEqual(unchanged.processes, processes)
	const swapped = applyProcessEdit(processes, mappings, [{ ...processes[0], sequence: 20 }, { ...processes[1], sequence: 10 }])
	assert.deepEqual(swapped.processes.map((row) => row.name), ["p2", "p1"])
	assert.deepEqual(swapped.mappings.map((row) => [row.name, row.sequence]), [["m2", 10], ["m3", 10], ["m1", 20]])
	const removed = removeProcess(processes, mappings, "p2")
	assert.deepEqual(removed.processes.map((row) => row.name), ["p1"])
	assert.deepEqual(removed.mappings.map((row) => row.name), ["m1"])
	assert.equal(orphanMappingCount(removed.processes, mappings), 2)
	assert.deepEqual(sortBySequence([{ sequence: 2, mapping_index: 1, n: 1 }, { sequence: 1, n: 2 }, { sequence: 2, mapping_index: 0, n: 3 }], ["sequence", "mapping_index"]).map((row) => row.n), [2, 3, 1])
}

function testRoutePairsFromRoutes() {
	const draft = { fabric_routes: [
		{ finished_colour: "White", finished_dia: "15 Dia" },
		{ finished_colour: "White", finished_dia: "14 Dia" },
		{ finished_colour: "Black", finished_dia: "14 Dia" },
		{ finished_colour: "White", finished_dia: "14 Dia" },
	] }
	const pairs = compactingRoutePairs(draft, ATTRIBUTES)
	assert.deepEqual(pairs, [{ colour: "Black", input_dia: "14 Dia" }, { colour: "White", input_dia: "14 Dia" }, { colour: "White", input_dia: "15 Dia" }])
	assert.deepEqual(pairColours(pairs), ["Black", "White"])
	assert.deepEqual(compactingTargets(pairs, "All Colours"), [{ colour: "", input_dia: "14 Dia" }, { colour: "", input_dia: "15 Dia" }])
	assert.deepEqual(compactingTargets(pairs, "Separate Colours"), pairs)
	assert.deepEqual(compactingTargets(pairs, "Colour Group", ["Black"]), [pairs[0]])
}

function testRoutePairsFromMappings() {
	const draft = { fabric_value_mappings: [
		{ sequence: 10, mapping_index: 0, attribute: "Colour", role: "Introduce", to_value: "Greige" },
		{ sequence: 10, mapping_index: 0, attribute: "Dia", role: "Introduce", to_value: "14 Dia" },
		{ sequence: 10, mapping_index: 1, attribute: "Dia", role: "Introduce", to_value: "15 Dia" },
		{ sequence: 20, mapping_index: 0, attribute: "Colour", role: "Change", from_value: "Greige", to_value: "Navy" },
	] }
	assert.deepEqual(compactingRoutePairs(draft, ATTRIBUTES), [
		{ colour: "Greige", input_dia: "14 Dia" }, { colour: "Navy", input_dia: "14 Dia" }, { colour: "Navy", input_dia: "15 Dia" },
	])
	const recipeOnly = { fabric_value_mappings: [{ sequence: 10, mapping_index: 0, attribute: "Dia", role: "Introduce", to_value: "9 Dia" }], colour_yarn_recipes: [{ colour: "Red" }, { colour: "Red" }] }
	assert.deepEqual(compactingRoutePairs(recipeOnly, ATTRIBUTES), [{ colour: "Red", input_dia: "9 Dia" }])
	assert.deepEqual(compactingRoutePairs({}, ATTRIBUTES), [])
}

function testAddTargetsIsAddOnly() {
	const rows = [{ name: "c1", colour: null, input_dia: "14 Dia", compacting_dia: "15 Dia" }]
	const result = addCompactingTargets(rows, [{ colour: "", input_dia: "14 Dia" }, { colour: "", input_dia: "15 Dia" }, { colour: "", input_dia: "15 Dia" }])
	assert.equal(result.added, 1)
	assert.equal(result.rows[0], rows[0])
	assert.deepEqual(result.rows[1], { colour: null, input_dia: "15 Dia", compacting_dia: null, notes: null })
	assert.equal(addCompactingTargets(result.rows, [{ colour: "", input_dia: "15 Dia" }]).added, 0)
}

function testFillCompactingDia() {
	const rows = [{ name: "a", colour: "White", input_dia: "14 Dia" }, { name: "b", colour: "Black", input_dia: "14 Dia" }, { name: "c", input_dia: "15 Dia" }]
	assert.deepEqual(compactingInputDias(rows), ["14 Dia", "15 Dia"])
	assert.match(fillCompactingDia(rows, [], "16 Dia").error, /Select/)
	assert.match(fillCompactingDia(rows, ["a", "c"], "16 Dia").error, /same/)
	assert.match(fillCompactingDia(rows, ["a"], "").error, /Choose/)
	const result = fillCompactingDia(rows, ["a", "b"], "16 Dia")
	assert.equal(result.updated, 2)
	assert.deepEqual(result.rows.map((row) => row.compacting_dia), ["16 Dia", "16 Dia", undefined])
	assert.equal(result.rows[2], rows[2])
}

function testStoredOptions() {
	const options = ["White"]
	assert.equal(withStoredOptions(options, [{ colour: "White" }], ["colour"]), options)
	assert.deepEqual(withStoredOptions(options, [{ colour: "Old" }, { colour: null }], ["colour"]), ["White", "Old"])
}

testRowModelRoundTrip()
testRatioTotal()
testProcessSequenceEdit()
testRoutePairsFromRoutes()
testRoutePairsFromMappings()
testAddTargetsIsAddOnly()
testFillCompactingDia()
testStoredOptions()
console.log("ipd cloth grid tests passed")
