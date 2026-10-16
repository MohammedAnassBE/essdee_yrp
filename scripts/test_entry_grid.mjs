#!/usr/bin/env node
import assert from "node:assert/strict"

import {
	applyBlock,
	clearRange,
	coerceCell,
	columnTotals,
	displayCell,
	fillDown,
	fillRight,
	moveCell,
	normalizeRange,
	parsePastedBlock,
	pasteReportText,
	rangeMatrix,
	rowTotal,
	sameForAll,
	toTsv,
} from "../frontend/src/components/common/entryGrid.js"

assert.deepEqual(parsePastedBlock("1\t2\r\n3\t4\r\n"), [["1", "2"], ["3", "4"]])
assert.deepEqual(parsePastedBlock("a\n"), [["a"]])
assert.deepEqual(parsePastedBlock('"x\ty"\t"he said ""hi"""\n"two\nlines"\tz'), [["x\ty", 'he said "hi"'], ["two\nlines", "z"]])
assert.deepEqual(parsePastedBlock("a\t\tb"), [["a", "", "b"]])
assert.deepEqual(parsePastedBlock(""), [])
assert.equal(toTsv([["a", 'b"c'], ["d\te", null]]), 'a\t"b""c"\n"d\te"\t')
assert.deepEqual(parsePastedBlock(toTsv([["x\ny", "1"]])), [["x\ny", "1"]])

assert.deepEqual(normalizeRange({ row: 3, col: 1 }, { row: 1, col: 2 }), { top: 1, bottom: 3, left: 1, right: 2 })

const bounds = { rows: 2, cols: 3 }
assert.deepEqual(moveCell({ row: 0, col: 0 }, "up", bounds), { row: 0, col: 0 })
assert.deepEqual(moveCell({ row: 0, col: 2 }, "right", bounds), { row: 0, col: 2 })
assert.deepEqual(moveCell({ row: 0, col: 1 }, "down", bounds), { row: 1, col: 1 })
const editable = (row, col) => col !== 1
assert.deepEqual(moveCell({ row: 0, col: 0 }, "next", bounds, editable), { row: 0, col: 2 })
assert.deepEqual(moveCell({ row: 0, col: 2 }, "next", bounds, editable), { row: 1, col: 0 })
assert.deepEqual(moveCell({ row: 1, col: 0 }, "previous", bounds, editable), { row: 0, col: 2 })
assert.deepEqual(moveCell({ row: 1, col: 2 }, "next", bounds, editable), { row: 0, col: 0 })

const number = { key: "qty", type: "number", min: 0, precision: 4 }
assert.deepEqual(coerceCell(number, " 1,234.56789 "), { value: 1234.5679, error: "" })
assert.deepEqual(coerceCell(number, ""), { value: null, error: "" })
assert.match(coerceCell(number, "abc").error, /not a number/)
assert.match(coerceCell(number, "-1").error, /0 or more/)
const select = { key: "category", type: "select", options: ["Body", "Main Panel"] }
assert.deepEqual(coerceCell(select, "main panel"), { value: "Main Panel", error: "" })
assert.match(coerceCell(select, "Rib").error, /not one of the allowed values/)
assert.deepEqual(coerceCell({ type: "value", options: [{ value: "Black", label: "Black" }] }, "BLACK"), { value: "Black", error: "" })
assert.deepEqual(coerceCell({ type: "link", options: [] }, " Cotton "), { value: "Cotton", error: "" })
assert.deepEqual(coerceCell({ type: "check" }, "Yes"), { value: 1, error: "" })
assert.deepEqual(coerceCell({ type: "check" }, "0"), { value: 0, error: "" })
assert.deepEqual(coerceCell({ type: "text" }, "TOP PIPING "), { value: "TOP PIPING ", error: "" })

const rows = [{ key: "S", label: "S" }, { key: "M", label: "M" }, { key: "L", label: "L", readonly: true }]
const columns = [
	{ key: "Black|dia", type: "text", field: "dia" },
	{ key: "Black|weight", type: "number", field: "weight", precision: 4 },
	{ key: "Navy|dia", type: "text", field: "dia" },
	{ key: "Navy|weight", type: "number", field: "weight", precision: 4 },
]
const model = { S: { "Black|dia": "32 Dia", "Black|weight": 0.1 } }
const frozen = structuredClone(model)

const pasted = applyBlock(model, rows, columns, { row: 1, col: 2 }, parsePastedBlock("30 Dia\t0.2\t9\nx\ty\n1\t2"))
assert.deepEqual(model, frozen)
assert.equal(pasted.applied, 2)
assert.equal(pasted.skipped, 3)
assert.equal(pasted.readonly, 2)
assert.deepEqual(pasted.invalid.map((cell) => [cell.rowKey, cell.colKey, cell.value]), [])
assert.deepEqual(pasted.model.M, { "Navy|dia": "30 Dia", "Navy|weight": 0.2 })
const bad = applyBlock({}, rows, columns, { row: 0, col: 1 }, [["abc"]])
assert.equal(bad.applied, 0)
assert.deepEqual(bad.invalid.map((cell) => [cell.rowKey, cell.colKey, cell.value]), [["S", "Black|weight", "abc"]])
assert.equal(pasteReportText({ rows: 3, cols: 3, skipped: 2, readonly: 0, invalid: [] }), "Pasted 3 × 3 · 2 cells outside the grid skipped")
assert.equal(pasteReportText({ rows: 1, cols: 1, skipped: 0, readonly: 1, invalid: [{}] }), "Pasted 1 × 1 · 1 read-only cell skipped · 1 value not allowed")

const right = fillRight(model, rows, columns, { top: 0, bottom: 0, left: 0, right: 2 })
assert.deepEqual(right.model.S, { "Black|dia": "32 Dia", "Black|weight": "32 Dia", "Navy|dia": "32 Dia" })
const rightSingle = fillRight(model, rows, columns, { top: 0, bottom: 0, left: 1, right: 1 })
assert.equal(rightSingle.model.S["Black|weight"], "32 Dia")
assert.deepEqual(fillRight(model, rows, columns, { top: 0, bottom: 0, left: 0, right: 0 }).changes, [])
const down = fillDown(model, rows, columns, { top: 0, bottom: 2, left: 0, right: 1 })
assert.deepEqual(down.model.M, { "Black|dia": "32 Dia", "Black|weight": 0.1 })
assert.equal(down.model.L, undefined)
const downSingle = fillDown(model, rows, columns, { top: 1, bottom: 1, left: 0, right: 0 })
assert.equal(downSingle.model.M["Black|dia"], "32 Dia")

const same = sameForAll(model, rows, columns, { top: 0, bottom: 0, left: 0, right: 1 })
assert.deepEqual(same.model.S, { "Black|dia": "32 Dia", "Black|weight": 0.1, "Navy|dia": "32 Dia", "Navy|weight": 0.1 })
const plainColumns = [{ key: "Olive", type: "select" }, { key: "Grey", type: "select" }, { key: "Note", type: "text" }]
const plainSame = sameForAll({ Front: { Olive: "Main" } }, [{ key: "Front" }], plainColumns, { top: 0, bottom: 0, left: 0, right: 0 })
assert.deepEqual(plainSame.model.Front, { Olive: "Main", Grey: "Main" })

const cleared = clearRange(pasted.model, rows, columns, { top: 1, bottom: 2, left: 2, right: 3 })
assert.deepEqual(cleared.model.M, { "Navy|dia": null, "Navy|weight": null })
assert.equal(cleared.changes.length, 2)

assert.deepEqual(rangeMatrix(same.model, rows, columns, { top: 0, bottom: 0, left: 0, right: 1 }), [["32 Dia", "0.1"]])
assert.equal(displayCell({ type: "check" }, 1), "✓")
assert.equal(displayCell({ type: "value", options: [{ value: "IAV-1", label: "Black" }] }, "IAV-1"), "Black")
assert.deepEqual(columnTotals({ S: { "Black|weight": 0.1 }, M: { "Black|weight": 0.2 } }, rows, columns), { "Black|weight": 0.3, "Navy|weight": 0 })
assert.equal(rowTotal(same.model, rows[0], columns), 0.2)

console.log("entry grid tests passed")
