import assert from "node:assert/strict"
import test from "node:test"
import { matchAttributeValues } from "../src/utils/stockItemComposer.js"

test("Attribute value search lists the exact value first, then prefixes, then other matches", () => {
	const values = ["White Melange", "Off white", "Bright White", "White", "Black"]
	assert.deepEqual(matchAttributeValues(values, "white"), ["White", "White Melange", "Off white", "Bright White"])
	assert.deepEqual(matchAttributeValues(values, ""), values)
})
