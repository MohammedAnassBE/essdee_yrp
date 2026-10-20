import assert from "node:assert/strict"
import test from "node:test"
import * as tables from "../src/departments/purchase/item/itemTables.js"
import { dependentDetailRows, itemDependentProblem, itemSaveValues } from "../src/departments/purchase/purchaseViews.js"

test("variants lock attribute rows while values and primary/dependent stay editable", () => {
	assert.deepEqual(tables.itemAttributeEditing({ attributes_locked: true, permissions: { can_write_item_attribute: true } }, true), {
		rows: false, values: true, primary: true, dependent: true, createValues: true,
	})
})

test("stock flags lock primary/dependent independently of editable mapping values", () => {
	assert.deepEqual(tables.itemAttributeEditing({ attributes_locked: true, primary_attribute_locked: true, dependent_attribute_locked: true }, true), {
		rows: false, values: true, primary: false, dependent: false, createValues: false,
	})
})

test("read-only permissions prevent all attribute edits and global value creation", () => {
	assert.deepEqual(tables.itemAttributeEditing({ permissions: { can_write_item_attribute: true } }, false), {
		rows: false, values: false, primary: false, dependent: false, createValues: false,
	})
})

test("items without variants allow attribute rows and existing value edits", () => {
	assert.deepEqual(tables.itemAttributeEditing({}, true), {
		rows: true, values: true, primary: true, dependent: true, createValues: false,
	})
})

test("missing primary on an item with variants still explains sticker and pricing requirements", () => {
	assert.deepEqual(tables.itemTableWarnings({ attributes: [{ attribute: "Size" }] }, { attributes_locked: true }), [
		"Box Sticker auto-create and size-wise pricing need a Primary Attribute.",
	])
})

test("missing primary with stock explains the lock instead of asking for an impossible edit", () => {
	assert.deepEqual(tables.itemTableWarnings({ attributes: [{ attribute: "Size" }] }, {
		primary_attribute_locked: true,
		primary_attribute_lock_message: "Primary Attribute is locked because YRP stock exists for this Item.",
	}), ["Box Sticker auto-create and size-wise pricing need a Primary Attribute. Primary Attribute is locked because YRP stock exists for this Item."])
})

test("missing primary with a stock flag has a meaningful fallback explanation", () => {
	assert.deepEqual(tables.itemTableWarnings({ attributes: [{ attribute: "Size" }] }, { primary_attribute_locked: true }), [
		"Box Sticker auto-create and size-wise pricing need a Primary Attribute. Primary Attribute is locked because YRP stock exists for this Item.",
	])
})

test("an existing primary does not produce a missing-primary warning even with stock", () => {
	assert.deepEqual(tables.itemTableWarnings({ attributes: [{ attribute: "Size" }], primary_attribute: "Size" }, { primary_attribute_locked: true }), [])
})

test("saving value edits preserves a deliberately empty primary on existing items", () => {
	const result = itemSaveValues({ attributes: [{ attribute: "Size", values: ["M", "L"] }], primary_attribute: "" }, { defaultSinglePrimary: false })
	assert.equal(result.primary_attribute, null)
	assert.deepEqual(result.attributes[0].values, ["M", "L"])
})

test("dependent picklist removal preserves independent configured stages", () => {
	const values = {
		primary_attribute: "Size", dependent_attribute: "Stage", dependent_mapping_modified: "existing",
		attributes: [{ attribute: "Stage", values: [] }, { attribute: "Size", values: ["M"] }],
		dependent_details: [{ value: "Cut", uom: "Piece", display_name: "Cut", attributes: ["Size"] }],
	}
	assert.deepEqual(dependentDetailRows(values, "Piece", { preserveExisting: true }), values.dependent_details)
	assert.equal(itemDependentProblem(values), "")
})

test("dependent picklist additions append defaults and retain earlier stages", () => {
	assert.deepEqual(dependentDetailRows({
		primary_attribute: "Size", dependent_attribute: "Stage",
		attributes: [{ attribute: "Stage", values: ["Pack"] }, { attribute: "Size", values: ["M"] }],
		dependent_details: [{ value: "Cut", uom: "Piece", display_name: "Cutting", attributes: ["Size"] }],
	}, "Piece", { preserveExisting: true }), [
		{ value: "Cut", uom: "Piece", display_name: "Cutting", attributes: ["Size"] },
		{ value: "Pack", uom: "Piece", display_name: "", attributes: ["Size"] },
	])
})

test("new dependent configuration still requires values and resets previous stages", () => {
	const values = {
		primary_attribute: "Size", dependent_attribute: "Stage",
		attributes: [{ attribute: "Stage", values: ["Pack"] }, { attribute: "Size", values: ["M"] }],
		dependent_details: [{ value: "Cut", uom: "Piece", attributes: ["Size"] }],
	}
	assert.deepEqual(dependentDetailRows(values, "Piece"), [{ value: "Pack", uom: "Piece", display_name: "", attributes: ["Size"] }])
	assert.equal(itemDependentProblem({ ...values, attributes: [] }), "Please configure values for Dependent Attribute Stage.")
})
