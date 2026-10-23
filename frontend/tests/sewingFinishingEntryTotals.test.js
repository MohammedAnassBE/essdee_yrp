import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { inputTotals, lotTransferTotals, referenceTotals, reworkTotals } from "../src/departments/finishing/finishingEntryTotals.js"
import { closedGrnRowTotal, closedGrnTotals, sewingMatrixTotals, sumQuantities } from "../src/departments/sewing/sewingQuantityTotals.js"

const source = (path) => readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")

test("sumQuantities ignores blanks and invalid input and rounds to 3 decimals", () => {
	assert.equal(sumQuantities(["0.1", 0.2, "", null, "abc", undefined]), 0.3)
	assert.equal(sumQuantities([]), 0)
	assert.equal(sumQuantities(), 0)
})

test("S9 Sewing matrix totals per colour, per size, grand and context columns", () => {
	const colours = {
		Red: { values: { S: { order_detail: "r-s", order_qty: 10 }, M: { order_detail: "r-m", order_qty: 5 } } },
		Blue: { values: { S: { order_detail: "b-s", order_qty: 4 } } },
	}
	const totals = sewingMatrixTotals(colours, ["S", "M"], { "r-s": "3", "r-m": 2.5, "b-s": "" }, [{ key: "order_qty" }])
	assert.deepEqual(totals.colours.Red, { quantity: 5.5, context: { order_qty: 15 } })
	assert.deepEqual(totals.colours.Blue, { quantity: 0, context: { order_qty: 4 } })
	assert.deepEqual(totals.sizes.S, { quantity: 3, context: { order_qty: 14 } })
	assert.deepEqual(totals.sizes.M, { quantity: 2.5, context: { order_qty: 5 } })
	assert.deepEqual(totals.grand, { quantity: 5.5, context: { order_qty: 19 } })
})

test("S9 Sewing matrix shows a Total column and a Total footer row", () => {
	const matrix = source("sewing/components/SewingQuantityMatrix.vue")
	assert.match(matrix, /<th scope="col" class="sewing-quantity-matrix__total">Total<\/th>/)
	assert.match(matrix, /<tfoot>[\s\S]*totals\.sizes\[size\]\.quantity[\s\S]*totals\.grand\.quantity[\s\S]*<\/tfoot>/)
})

test("Closed Work Order GRN totals received and pending per UOM, skipping cells without a receivable", () => {
	const rows = [
		{ default_uom: "Nos", values: { S: { qty: 2, pending_quantity: 5, ref_docname: "a" }, M: { qty: 1, pending_quantity: 2, ref_docname: "b" } } },
		{ default_uom: "Nos", values: { S: { qty: 4, pending_quantity: 4, ref_docname: "c" }, M: { qty: 9 } } },
		{ default_uom: "Kg", values: { S: { qty: 1.5, pending_quantity: 3, ref_docname: "d" } } },
		{ default_uom: "Kg", values: { S: { qty: 2, pending_quantity: 3, ref_docname: "d" } } },
	]
	const [nos, kg] = closedGrnTotals(rows, ["S", "M"])
	assert.deepEqual(nos, { uom: "Nos", sizes: { S: { qty: 6, pending: 9 }, M: { qty: 1, pending: 2 } }, qty: 7, pending: 11 })
	assert.equal(kg.uom, "Kg")
	assert.equal(kg.qty, 3.5)
	assert.equal(kg.pending, 3)
	assert.equal(closedGrnRowTotal(rows[1], ["S", "M"]), 4)
	assert.deepEqual(closedGrnTotals([], ["S"]), [])
})

test("S8 Finishing entry totals across colours for references and the entered quantity", () => {
	const rows = { Red: { values: { S: { balance: 10 }, M: { balance: 4 } } }, Blue: { values: { S: { balance: 3 } } } }
	assert.deepEqual(referenceTotals(rows, ["Red", "Blue"], ["S", "M"], "balance"), { sizes: { S: 13, M: 4 }, total: 17 })
	const entry = { Red: { checked: true, sizes: { S: "2", M: "1.25" } }, Blue: { checked: false, sizes: { S: 3, M: "" } } }
	assert.deepEqual(inputTotals(entry, ["Red", "Blue"], ["S", "M"]), { sizes: { S: 5, M: 1.25 }, total: 6.25 })
	assert.deepEqual(inputTotals(entry, ["Red", "Blue"], ["S", "M"], true), { sizes: { S: 2, M: 1.25 }, total: 3.25 })
})

test("S8 Finishing entry matrix renders a Total footer for references and input", () => {
	const matrix = source("finishing/components/FinishingEntryMatrix.vue")
	assert.match(matrix, /<tfoot>[\s\S]*totals\.references\[reference\.key\]\.total[\s\S]*totals\.input\.total[\s\S]*<\/tfoot>/)
})

test("Rework entry totals and old lot transfer totals", () => {
	assert.deepEqual(reworkTotals([{ rework_qty: 5, rejected: "1", rework: 2 }, { rework_qty: 3, rejected: "", rework: "1.5" }]), { rework_qty: 8, rejected: 1, rework: 3.5 })
	const row = { primary_values: ["S", "M"], old_lot_inward: { data: { Red: { values: { S: { balance_loose_piece: 4 }, M: { balance_loose_piece: 2 } } }, Blue: { values: { S: { balance_loose_piece: 1 } } } } } }
	const transfer = { Red: { sizes: { S: { loose_piece: "2" }, M: { loose_piece: 1 } } }, Blue: { sizes: { S: { loose_piece: 1 }, M: { loose_piece: 0 } } } }
	assert.deepEqual(lotTransferTotals(row, transfer, "loose_piece", "balance_loose_piece"), {
		balance: { sizes: { S: 5, M: 2 }, total: 7 },
		transfer: { sizes: { S: 3, M: 1 }, total: 4 },
	})
	assert.match(source("finishing/components/FinishingReworkEntry.vue"), /totals\.rejected[\s\S]*totals\.rework\b/)
	assert.match(source("finishing/plan/FinishingOldLotTab.vue"), /<tfoot>[\s\S]*bucketTotals\(row\)[\s\S]*<\/tfoot>/)
})
