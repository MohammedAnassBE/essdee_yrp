#!/usr/bin/env node

import assert from "node:assert/strict"

import { groupRowInputs, groupRowPayload, reworkRowsError, rowTotal } from "../frontend/src/departments/finishing/reports/reworkRules.js"

const items = [{ Size: "S", rework_qty: 5, rejected: 1, rework: 2, row_name: "d1" }, { Size: "M", rework_qty: 3, rejected: 0, rework: 0, row_name: "d2" }]
assert.equal(reworkRowsError(items), "")
assert.equal(reworkRowsError([{ ...items[0], rejected: 6 }]), "Rejected quantity must be between 0 and the pending quantity.")
assert.equal(reworkRowsError([{ ...items[0], rework: -1 }]), "Reworked quantity must be between 0 and the pending quantity.")
assert.equal(reworkRowsError([{ ...items[0], rejected: "x" }]), "Rejected quantity must be between 0 and the pending quantity.")
assert.equal(reworkRowsError([{ ...items[0], rework: 0 }, items[1]], true), "Enter at least one Reworked quantity.")

const row = { rejection: { S: 1 }, items }
const inputs = groupRowInputs(row, ["S", "M"])
assert.deepEqual(inputs, { rejection: { S: 1, M: 0 }, rework: { S: 0, M: 0 } })
inputs.rejection.M = 2
inputs.rework.S = 3
assert.deepEqual(groupRowPayload(row, inputs, "Size", "rejection").map((item) => [item.row_name, item.rejected, item.rework]), [["d1", 1, 2], ["d2", 2, 0]])
assert.deepEqual(groupRowPayload(row, inputs, "Size", "rework").map((item) => [item.row_name, item.rejected, item.rework]), [["d1", 1, 3], ["d2", 0, 0]])
assert.equal(rowTotal({ S: 1, M: "2" }, ["S", "M", "L"]), 3)

console.log("Finishing rework rules: OK")
