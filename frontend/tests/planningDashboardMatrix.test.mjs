import test from "node:test"
import assert from "node:assert/strict"

import { ALL_COLOURS, colourWiseMatrix, sizeWiseMatrix } from "../src/departments/planning/dashboard/detailMatrix.js"

const itemDetail = {
	kind: "item", sizes: ["M", "L"], packing: null,
	grid: [{ colour: "Black", part: "", planned: { M: 100, L: 50 }, delivered: { M: 100, L: 50 }, received: { M: 90, L: 50 } }],
}
const packingDetail = {
	kind: "packing", sizes: ["M", "L"],
	grid: [
		{ colour: "Black", part: "", planned: { M: 100, L: 50 }, delivered: { M: 100, L: 40 }, received: {} },
		{ colour: "Red", part: "", planned: { M: 10 }, delivered: { M: 10 }, received: {} },
	],
	packing: { planned: { M: 110, L: 50 }, delivered: { M: 110, L: 40 }, received: { M: 100, L: 40 }, dispatch: { M: 90, L: 0 } },
}
const line = (row, key) => row.lines.find((entry) => entry.key === key)

test("size-wise rows are colours with Planned, Delivered, Received and Difference against delivered", () => {
	const matrix = sizeWiseMatrix(itemDetail)
	assert.deepEqual(matrix.columns, ["M", "L"])
	const black = matrix.rows[0]
	assert.deepEqual(black.lines.map((entry) => entry.label), ["Planned", "Delivered", "Received", "Difference"])
	assert.deepEqual(line(black, "difference").cells.map((cell) => cell.text), ["-10", "0"])
	assert.equal(line(black, "difference").total.text, "-10")
	assert.equal(line(black, "received").cells[0].tone, "part")
	assert.equal(line(black, "delivered").cells[0].tone, "ok")
})

test("cutting shows no delivered pieces and compares received with planned", () => {
	const matrix = sizeWiseMatrix({ ...itemDetail, kind: "cutting" })
	assert.equal(line(matrix.rows[0], "delivered").cells[0].text, "—")
	assert.equal(line(matrix.rows[0], "difference").cells[0].text, "-10")
})

test("packing colour rows carry Planned and Delivered; All colours carries Received and Dispatch", () => {
	const matrix = sizeWiseMatrix(packingDetail)
	assert.deepEqual(matrix.rows.map((row) => row.key), ["Black", "Red", ALL_COLOURS])
	assert.equal(matrix.rows[0].lines.length, 2)
	const all = matrix.rows[2]
	assert.deepEqual(all.lines.map((entry) => entry.label), ["Planned", "Delivered", "Received", "Dispatch", "Difference"])
	assert.deepEqual(line(all, "planned").cells.map((cell) => cell.value), [110, 50])
	assert.equal(line(all, "received").total.value, 140)
	assert.equal(line(all, "dispatch").total.value, 90)
})

test("colour-wise rows are sizes and packing totals come from the per-size figures", () => {
	const matrix = colourWiseMatrix(packingDetail)
	assert.deepEqual(matrix.columns, ["Black", "Red"])
	const medium = matrix.rows[0]
	assert.equal(medium.key, "M")
	assert.equal(line(medium, "received").cells[0].text, "—")
	assert.equal(line(medium, "received").total.value, 100)
	assert.equal(line(medium, "planned").total.value, 110)
})

test("parts join the colour label", () => {
	const matrix = sizeWiseMatrix({ ...itemDetail, grid: [{ ...itemDetail.grid[0], part: "Top" }] })
	assert.equal(matrix.rows[0].key, "Black · Top")
})
