#!/usr/bin/env node

import assert from "node:assert/strict"

import {
	completedReportSections,
	completionLabel,
} from "../frontend/src/departments/cutting/cuttingCompletedReport.js"

const normalGroup = {
	attributes: ["Colour"],
	primary_attribute_values: ["S", "M"],
	stiching_attr: "Panel",
	Panel: ["Front", "Back"],
	items: [
		{ name: "navy", attributes: { Colour: "Navy" }, values: { S: 4, M: 5 }, completed: true },
		{ name: "red", attributes: { Colour: "Red" }, values: { S: 2, M: 3 }, completed: false },
	],
}

const completedOnly = completedReportSections([normalGroup])
assert.equal(completedOnly.length, 1)
assert.deepEqual(completedOnly[0].items.map((item) => item.name), ["navy"])
assert.deepEqual(completedOnly[0].panels, ["Front", "Back"])

const allRows = completedReportSections([normalGroup], true)
assert.deepEqual(allRows[0].items.map((item) => item.name), ["navy", "red"])
assert.equal(completionLabel(allRows[0].items[0]), "Completed")
assert.equal(completionLabel(allRows[0].items[1]), "Not completed")

const setGroup = {
	is_set_item: true,
	set_item_attr: "Part",
	stiching_attr: "Panel",
	attributes: ["Colour", "Part"],
	primary_attribute_values: ["S"],
	Panel: { Top: ["Front", "Back"], Bottom: ["Leg"] },
	items: [
		{ name: "top", attributes: { Colour: "Green", Part: "Top" }, values: { S: 10 }, completed: false },
		{ name: "bottom", attributes: { Colour: "Green", Part: "Bottom" }, values: { S: 8 }, completed: true },
	],
}
const setSections = completedReportSections([setGroup], true)
assert.deepEqual(setSections.map((section) => section.part), ["Top", "Bottom"])
assert.deepEqual(setSections.map((section) => section.items.map((item) => item.name)), [["top"], ["bottom"]])
assert.deepEqual(completedReportSections([setGroup]).map((section) => section.part), ["Bottom"])

const requests = []
globalThis.window = { csrf_token: "" }
globalThis.fetch = async (url, options) => {
	requests.push({ url, body: JSON.parse(options.body) })
	return { ok: true, status: 200, json: async () => ({ message: { lots: [] } }) }
}
const { getLotCutQuantity } = await import("../frontend/src/api/purchaseReports.js")
await getLotCutQuantity(["LOT-B", "LOT-A"])
assert.equal(requests[0].url, "/api/method/essdee_yrp.purchase.lot_cut_quantity.get_lot_cut_quantity")
assert.deepEqual(requests[0].body.lots, ["LOT-B", "LOT-A"])

console.log("Lot Cut Quantity report: OK")
