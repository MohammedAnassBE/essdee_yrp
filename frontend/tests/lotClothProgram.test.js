import assert from "node:assert/strict"
import test from "node:test"
import { programDia, programColour, programDias, programColourColumns, programRow, serializeClothProgram } from "../src/engine/lotClothProgram.js"

const route = (finishedColour, finishedDia, weight) => ({
	dia: "18 Dia", colour: "Greige", finished_colour: finishedColour, finished_dia: finishedDia,
	reference_item_variant: `Cloth-${finishedDia}-${finishedColour}`, weight,
})

test("the matrix shows finished colours, even when knitting outputs the same greige variant", () => {
	const entry = { program: [route("Red", "22 Dia", 100), route("Navy", "22 Dia", 80)] }
	assert.deepEqual(programColourColumns(entry), [{ key: "Navy", label: "Navy" }, { key: "Red", label: "Red" }])
	assert.deepEqual(programDias(entry), ["22 Dia"])
	assert.equal(programRow(entry, "22 Dia", "Red").weight, 100)
	assert.equal(programRow(entry, "18 Dia", "Greige"), undefined)
})

test("editing a final-colour cell saves the original physical attributes and reference", () => {
	const entry = { cloth_item: "Cloth", program: [route("Red", "22 Dia", 100), route("Navy", "22 Dia", 80)] }
	programRow(entry, "22 Dia", "Red").weight = 95.125
	const saved = serializeClothProgram([entry])
	assert.deepEqual(saved[0].program[0], { dia: "18 Dia", colour: "Greige", reference_item_variant: "Cloth-22 Dia-Red", weight: 95.125 })
	assert.equal(saved[0].program[1].weight, 80)
	assert.equal(entry.program[0].finished_colour, "Red")
	assert.equal("finished_colour" in saved[0].program[0], false)
})

test("multiple dias sort numerically and do not duplicate a dia for different colours", () => {
	const entry = { program: [route("Red", "22 Dia", 1), route("Red", "8 Dia", 2), route("Navy", "22 Dia", 3), route("Red", "18.5 Dia", 4)] }
	assert.deepEqual(programDias(entry), ["8 Dia", "18.5 Dia", "22 Dia"])
})

test("legacy rows without a finished reference still display and round-trip", () => {
	const row = { dia: "24 Dia", colour: "Grey", weight: 0 }
	assert.equal(programDia(row), "24 Dia")
	assert.equal(programColour(row), "Grey")
	assert.deepEqual(serializeClothProgram([{ cloth_item: "Cloth", program: [row] }])[0].program[0], { ...row, reference_item_variant: null })
})

test("an empty program has a stable placeholder column and no fabricated rows", () => {
	assert.deepEqual(programDias({ program: [] }), [])
	assert.deepEqual(programColourColumns({ program: [] }), [{ key: "", label: "Program" }])
	assert.deepEqual(serializeClothProgram([]), [])
})
