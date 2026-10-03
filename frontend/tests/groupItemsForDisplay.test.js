// Tests the Essdee-owned route-split display aggregation.
import assert from "node:assert/strict"
import test from "node:test"

import * as displayRows from "../src/engine/stock/groupItemsForDisplay.js"
import {
	countItemsForDisplay,
	groupItemsForDisplay,
	setAggregatedCellQuantity,
	setAggregatedItemField,
} from "../src/engine/stock/groupItemsForDisplay.js"

const group = (items) => [{
	attributes: ["Dia", "Colour"],
	primary_attribute: "",
	primary_attribute_values: [],
	items,
}]

const item = (name, attributes, qty, reference, extra = {}) => ({
	name,
	attributes,
	dimensions: {},
	primary_attribute: "",
	default_uom: "Kg",
	fabric_reference_variant: reference,
	values: {
		default: {
			qty,
			pending_quantity: qty,
			cost: 2,
			...extra,
		},
	},
})

test("groups route-split rows without mutating the source", () => {
	const source = group([
		item("Cloth", { Dia: "36 Dia", Colour: "Greige" }, 41, "Cloth-36-Grey"),
		item("Cloth", { Dia: "36 Dia", Colour: "Greige" }, 41, "Cloth-36-Red"),
		item("Cloth", { Dia: "34 Dia", Colour: "Greige" }, 68, "Cloth-34-Red"),
	])

	const result = groupItemsForDisplay(source)

	assert.equal(result[0].items.length, 2)
	assert.deepEqual(result[0].items[0].values.default, {
		qty: 82,
		pending_quantity: 82,
		cost: 2,
	})
	assert.equal(result[0].items[0].fabric_reference_variant, undefined)
	assert.equal(source[0].items.length, 3)
	assert.equal(source[0].items[0].fabric_reference_variant, "Cloth-36-Grey")
})

test("does not merge rows with different unit costs", () => {
	const source = group([
		item("Cloth", { Dia: "36 Dia", Colour: "Greige" }, 41, "Cloth-36-Grey"),
		item(
			"Cloth",
			{ Dia: "36 Dia", Colour: "Greige" },
			41,
			"Cloth-36-Red",
			{ cost: 3 },
		),
	])

	assert.equal(groupItemsForDisplay(source)[0].items.length, 2)
})

test("accepts reactive-style Proxy rows", () => {
	const proxied = new Proxy(
		item("Yarn", {}, 10, "Cloth-36-Grey"),
		{},
	)
	const source = group([
		proxied,
		item("Yarn", {}, 15, "Cloth-36-Red"),
	])

	assert.equal(groupItemsForDisplay(source)[0].items[0].values.default.qty, 25)
})

test("display counts use the same aggregation as the rendered rows", () => {
	const source = group([
		item("Yarn", {}, 20, "Cloth-36-Black"),
		item("Yarn", {}, 30, "Cloth-36-Grey"),
		item("Yarn", {}, 25, "Cloth-36-Maroon"),
		item("Yarn", {}, 26, "Cloth-36-Navy"),
		item("Yarn", {}, 45, "Cloth-36-Red"),
	])

	assert.equal(countItemsForDisplay(source, false), 5)
	assert.equal(countItemsForDisplay(source, true), 1)
})

test("calculation feedback reports physical rows instead of lineage rows", () => {
	assert.equal(typeof displayRows.countCalculatedItemsForDisplay, "function")
	const deliverables = group([
		item("Cloth", { Dia: "22 Dia", Colour: "Red" }, 1, "route-1"),
		item("Cloth", { Dia: "22 Dia", Colour: "Red" }, 2, "route-2"),
		item("Cloth", { Dia: "28 Dia", Colour: "Red" }, 3, "route-3"),
	])
	const receivables = group([
		item("Cloth", { Dia: "22 Dia", Colour: "Red" }, 1, "route-1"),
		item("Cloth", { Dia: "22 Dia", Colour: "Red" }, 2, "route-2"),
	])

	assert.deepEqual(
		displayRows.countCalculatedItemsForDisplay(
			{ deliverables, receivables },
			{ deliverables: 3, receivables: 2 },
		),
		{ deliverables: 2, receivables: 1 },
	)
})

test("quantity totals are rounded to stock precision for display", () => {
	assert.equal(typeof displayRows.sumItemQuantities, "function")
	const source = group([
		item("Cloth", { Dia: "22 Dia" }, 0.1, "route-1"),
		item("Cloth", { Dia: "28 Dia" }, 0.2, "route-2"),
	])

	assert.equal(displayRows.sumItemQuantities(source), 0.3)
})

test("editable aggregation ignores route references and distributes a total proportionally", () => {
	const source = group([
		item("Yarn", {}, 29, "Cloth-36-Black", { amount: 290, delivered_quantity: 29, stock_qty: 29, ref_doctype: "Work Order Deliverables", ref_docname: "row-1" }),
		item("Yarn", {}, 29, "Cloth-36-Grey", { amount: 290, delivered_quantity: 29, stock_qty: 29, ref_doctype: "Work Order Deliverables", ref_docname: "row-2" }),
		item("Yarn", {}, 26, "Cloth-36-Maroon", { amount: 260, delivered_quantity: 26, stock_qty: 26, ref_doctype: "Work Order Deliverables", ref_docname: "row-3" }),
		item("Yarn", {}, 33, "Cloth-36-Navy", { amount: 330, delivered_quantity: 33, stock_qty: 33, ref_doctype: "Work Order Deliverables", ref_docname: "row-4" }),
		item("Yarn", {}, 29, "Cloth-36-Red", { amount: 290, delivered_quantity: 29, stock_qty: 29, ref_doctype: "Work Order Deliverables", ref_docname: "row-5" }),
	])
	const displayItem = groupItemsForDisplay(source)[0].items[0]

	assert.equal(groupItemsForDisplay(source)[0].items.length, 1)
	assert.equal(displayItem.values.default.amount, 1460)
	setAggregatedCellQuantity(displayItem, "default", 100)
	assert.deepEqual(
		source[0].items.map((entry) => entry.values.default.qty),
		[19.863, 19.863, 17.808, 22.603, 19.863],
	)
	assert.equal(
		source[0].items.reduce((sum, entry) => sum + entry.values.default.qty, 0),
		100,
	)
})

test("an aggregated row comment is preserved on every underlying route row", () => {
	const source = group([
		item("Yarn", {}, 10, "Cloth-36-Grey"),
		item("Yarn", {}, 20, "Cloth-36-Red"),
	])
	const displayItem = groupItemsForDisplay(source)[0].items[0]

	setAggregatedItemField(displayItem, "comments", "Send in one bag")
	assert.deepEqual(source[0].items.map((entry) => entry.comments), ["Send in one bag", "Send in one bag"])
})
