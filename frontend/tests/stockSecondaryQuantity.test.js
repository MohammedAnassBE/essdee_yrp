import assert from "node:assert/strict"
import test from "node:test"
import { offersSecondaryQuantity } from "../src/utils/stockItemComposer.js"

test("secondary qty is offered where production_api offers it and the Item has a Secondary UOM", () => {
	const fabric = { secondary_uom: "Roll" }
	for (const operation of ["stock_entry", "stock_update", "purchase_order"]) {
		assert.equal(offersSecondaryQuantity(operation, fabric), true, operation)
	}
	for (const operation of ["stock_reconciliation", "lot_transfer"]) {
		assert.equal(offersSecondaryQuantity(operation, fabric), false, operation)
	}
	assert.equal(offersSecondaryQuantity("stock_entry", { secondary_uom: "" }), false)
	assert.equal(offersSecondaryQuantity("stock_entry", null), false)
})
