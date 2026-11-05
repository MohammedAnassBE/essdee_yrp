import assert from "node:assert/strict"
import test from "node:test"

import { applyBoxQuantity, splitPieces } from "../src/departments/finishing/plan/finishingBoxQuantities.js"

function setup(colours, { part = {} } = {}) {
	const data = Object.fromEntries(colours.map((colour) => [colour, { part: part[colour], values: { S: {}, M: {} } }]))
	const entry = Object.fromEntries(colours.map((colour) => [colour, { checked: true, sizes: { S: 0, M: 0 } }]))
	return { payload: { data: { data } }, entry }
}

const sizeValues = (entry, size) => Object.fromEntries(Object.entries(entry).map(([colour, row]) => [colour, row.sizes[size]]))

test("splitPieces splits equally and puts the remainder on the first colours", () => {
	assert.deepEqual(splitPieces(30, [1, 1, 1]), [10, 10, 10])
	assert.deepEqual(splitPieces(32, [1, 1, 1]), [11, 11, 10])
	assert.deepEqual(splitPieces(10, [3, 2]), [6, 4])
	assert.deepEqual(splitPieces(11, [3, 2, 0]), [7, 4, 0])
})

test("Box Qty splits boxes x pieces per box equally across colours", () => {
	const { payload, entry } = setup(["Red", "Blue", "Green"])
	assert.equal(applyBoxQuantity({ payload, entry, size: "S", boxes: 4, piecesPerBox: 8 }), true)
	assert.deepEqual(sizeValues(entry, "S"), { Red: 11, Blue: 11, Green: 10 })
	assert.deepEqual(sizeValues(entry, "M"), { Red: 0, Blue: 0, Green: 0 })
})

test("Box Qty follows the IPD colour ratio when one is set", () => {
	const { payload, entry } = setup(["Red", "Blue", "Green"])
	applyBoxQuantity({ payload, entry, size: "M", boxes: 3, piecesPerBox: 5, ratio: { Red: 3, Blue: 2 } })
	assert.deepEqual(sizeValues(entry, "M"), { Red: 9, Blue: 6, Green: 0 })
})

test("colour quantities stay editable after a Box Qty prefill", () => {
	const { payload, entry } = setup(["Red", "Blue"])
	applyBoxQuantity({ payload, entry, size: "S", boxes: 2, piecesPerBox: 10 })
	entry.Red.sizes.S = 7
	assert.deepEqual(sizeValues(entry, "S"), { Red: 7, Blue: 10 })
})

test("unknown pieces per box, blank or zero Box Qty leave the quantities as they are", () => {
	const { payload, entry } = setup(["Red", "Blue"])
	entry.Red.sizes.S = 5
	for (const [boxes, piecesPerBox] of [[3, null], [3, 0], [3, ""], ["", 10], [0, 10]]) {
		assert.equal(applyBoxQuantity({ payload, entry, size: "S", boxes, piecesPerBox }), false)
	}
	assert.deepEqual(sizeValues(entry, "S"), { Red: 5, Blue: 0 })
})

test("unchecked colours and colours without the size are skipped", () => {
	const { payload, entry } = setup(["Red", "Blue", "Green"])
	entry.Blue.checked = false
	delete entry.Green.sizes.S
	applyBoxQuantity({ payload, entry, size: "S", boxes: 1, piecesPerBox: 6, checkable: true })
	assert.deepEqual(entry.Red.sizes.S, 6)
	assert.equal(entry.Blue.sizes.S, 0)
	assert.equal("S" in entry.Green.sizes, false)
})

test("set items fill every part with the full box count, matching the ratio by major colour", () => {
	const colours = ["Red (Red) @ Top", "Blue (Blue) @ Top", "Red (Red) @ Bottom", "Blue (Blue) @ Bottom"]
	const part = Object.fromEntries(colours.map((colour) => [colour, colour.split("@ ")[1]]))
	const { payload, entry } = setup(colours, { part })
	payload.is_set_item = 1
	applyBoxQuantity({ payload, entry, size: "S", boxes: 2, piecesPerBox: 5, ratio: { Red: 3, Blue: 2 } })
	assert.deepEqual(sizeValues(entry, "S"), { "Red (Red) @ Top": 6, "Blue (Blue) @ Top": 4, "Red (Red) @ Bottom": 6, "Blue (Blue) @ Bottom": 4 })
})
