import assert from "node:assert/strict"
import test from "node:test"

import * as planning from "../src/departments/planning/lot/lotEditor.js"
import * as purchase from "../src/departments/purchase/lot/lotEditor.js"

for (const [name, editor] of [["purchase", purchase], ["planning", planning]]) {
	test(`${name} Lot editor explains the Production Order IPD lock`, () => {
		assert.equal(editor.lotFieldDescription({ fieldname: "production_order", read_only: true }), "Locked once an IPD is linked.")
		assert.equal(editor.lotFieldDescription({ fieldname: "production_order", read_only: false }), "Submitted PPOs for this item only.")
		assert.equal(editor.lotFieldDescription({ fieldname: "size_set_colour", options: "" }), "Options appear after Lot Order Details exist.")
		assert.equal(editor.lotFieldDescription({ fieldname: "season", description: "Kept" }), "Kept")
	})

	test(`${name} Lot editor offers submitted PPOs for the Lot item`, () => {
		assert.deepEqual(editor.lotLinkFilters("production_order", { item: "TSHIRT" }), { docstatus: 1, item: "TSHIRT" })
		assert.deepEqual(editor.lotLinkFilters("production_order", {}), { docstatus: 1 })
	})
}
