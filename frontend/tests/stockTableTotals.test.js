import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { getReturnTotalsByUom, getTableTotals } from "../src/engine/stock/deliveryChallanTotals.js"

const source = (name) => readFileSync(new URL(`../src/departments/fabric-store/${name}`, import.meta.url), "utf8")

test("table totals sum each size, secondary quantity, row total and value live", () => {
	const rows = [
		{ uom: "Nos", values: { S: { qty: 1.1, pending_qty: 5, secondary_qty: 0.2, secondary_uom: "Kg" }, M: { qty: 2, pending_qty: 3 } } },
		{ uom: "Nos", values: { S: { qty: 2.2, pending_qty: 4, secondary_qty: 0.1, secondary_uom: "Kg" }, M: { qty: "3" } } },
	]
	const amount = (row) => Object.values(row.values).reduce((sum, cell) => sum + Number(cell.qty) * 10, 0)
	let totals = getTableTotals(rows, ["S", "M"], { amount })
	assert.deepEqual(totals.quantities, { S: 3.3, M: 5 })
	assert.deepEqual(totals.pending, { S: 9, M: 3 })
	assert.deepEqual(totals.secondary, { S: 0.3, M: 0 })
	assert.equal(totals.total, 8.3)
	assert.equal(totals.amount, 83)
	rows[0].values.M.qty = 7
	totals = getTableTotals(rows, ["S", "M"])
	assert.equal(totals.quantities.M, 10)
	assert.equal(totals.total, 13.3)
	assert.equal(totals.amount, null)
})

test("table totals never add different units together", () => {
	const rows = [
		{ default_uom: "Kg", values: { default: { qty: 2, secondary_qty: 1, secondary_uom: "Roll" } } },
		{ default_uom: "Meter", values: { default: { qty: 3, secondary_qty: 4, secondary_uom: "Bag" } } },
	]
	const totals = getTableTotals(rows, ["default"], { pending: (cell) => cell.max_receivable_quantity })
	assert.equal(totals.quantities.default, null)
	assert.equal(totals.pending.default, null)
	assert.equal(totals.secondary.default, null)
	assert.equal(totals.total, null)
	assert.deepEqual(getTableTotals([], ["default"]).quantities, { default: 0 })
})

test("return totals group by UOM", () => {
	const rows = [
		{ uom: "Kg", delivered_quantity: 10, consumed_quantity: 2, already_returned: 1, returnable_quantity: 7, return_quantity: 2.5 },
		{ uom: "Kg", delivered_quantity: 5, consumed_quantity: 0, already_returned: 0, returnable_quantity: 5, return_quantity: null },
		{ uom: "Nos", delivered_quantity: 4, consumed_quantity: 1, already_returned: 0, returnable_quantity: 3, return_quantity: 3 },
	]
	assert.deepEqual(getReturnTotalsByUom(rows), [
		{ uom: "Kg", delivered_quantity: 15, consumed_quantity: 2, already_returned: 1, returnable_quantity: 12, return_quantity: 2.5 },
		{ uom: "Nos", delivered_quantity: 4, consumed_quantity: 1, already_returned: 0, returnable_quantity: 3, return_quantity: 3 },
	])
	assert.deepEqual(getReturnTotalsByUom(), [])
})

test("entry tables and return popups render a Total footer", () => {
	for (const name of ["DeliveryChallanWorkspace.vue", "GoodsReceivedNoteWorkspace.vue"]) {
		const text = source(name)
		assert.match(text, /<tr v-for="totals in \[tableTotals\(section\)\]"/)
		assert.match(text, /getTableTotals\(section\.items, primaryValues\(section\.group\)/)
	}
	assert.match(source("GoodsReceivedNoteWorkspace.vue"), /\{ pending: availableQuantity, amount: rowValue \}/)
	assert.equal(source("GoodsReceivedNoteWorkspace.vue").match(/@input="row\.values[^"]*= \$event\.value; markDirty\(\)"/g).length, 4)
	assert.equal(source("DeliveryChallanWorkspace.vue").match(/@input="setDisplay(Secondary)?Quantity\(row, [^"]*\$event\.value\)"/g).length, 4)
	assert.match(source("DeliveryChallanWorkspace.vue"), /delivery-challan-matrix__fill/)
	for (const name of ["DeliveryChallanReturnPanel.vue", "DeliveryChallanReturnDialog.vue"]) {
		assert.match(source(name), /const returnTotals = computed\(\(\) => getReturnTotalsByUom\(rows\.value\)\)/)
		assert.match(source(name), /<tr v-for="total in returnTotals"/)
		assert.match(source(name), /@input="row\.return_quantity = \$event\.value"/)
	}
})
