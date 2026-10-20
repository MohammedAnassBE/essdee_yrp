import assert from "node:assert/strict"
import test from "node:test"
import { buildProductionOrderPrintUrl, needsProductionOrderPrintDialog, getProductionOrderPrintDescription, validateProductionOrderPiecesPerBox } from "../src/utils/productionOrderPrint.js"

test("Production Order print URL encodes identity and includes pieces without letterhead parameters", () => {
	const url = buildProductionOrderPrintUrl({ doctype: "YRP Production Order", name: "PPO/1 & 2#x", piecesPerBox: 7 })
	assert.equal(url, "/printview?doctype=YRP+Production+Order&name=PPO%2F1+%26+2%23x&trigger_print=1&format=Essdee+Production+Order&pieces_per_box=7")
	const query = new URL(url, "https://test.local").searchParams
	assert.equal(query.get("name"), "PPO/1 & 2#x")
	assert.equal(query.get("pieces_per_box"), "7")
	assert.equal(query.has("no_letterhead"), false)
})
test("only positive configured pieces per box skip the dialog", () => {
	for (const pieces_per_box of [5, "10"]) assert.equal(needsProductionOrderPrintDialog({ pieces_per_box }), false)
	for (const pieces_per_box of [0, -1, null, undefined]) assert.equal(needsProductionOrderPrintDialog({ pieces_per_box }), true)
})
test("pieces per box validation treats zero as missing like the Desk Int field", () => {
	for (const value of [null, undefined, "", 0, "0"]) assert.equal(validateProductionOrderPiecesPerBox(value), "Pieces per Box is required.")
	for (const value of [-1, "-3"]) assert.equal(validateProductionOrderPiecesPerBox(value), "Pieces per Box must be greater than zero.")
	for (const value of [2.5, "abc"]) assert.equal(validateProductionOrderPiecesPerBox(value), "Pieces per Box must be a whole number greater than zero")
	for (const value of [1, 7, "5"]) assert.equal(validateProductionOrderPiecesPerBox(value), "")
})
test("dialog descriptions match the legacy FG master messages", () => {
	assert.equal(getProductionOrderPrintDescription(true), "Pieces per Box is not configured in FG Item Master.")
	assert.equal(getProductionOrderPrintDescription(false), "The item is not available in FG Item Master.")
})
