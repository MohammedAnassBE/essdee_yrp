import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = readFileSync(new URL("../src/departments/purchase/lot/LotFabricTab.vue", import.meta.url), "utf8")
const matrices = source.slice(source.indexOf("function fabricMatrices"), source.indexOf("function legacyRows"))

test("Lot Cloth Program shows only the rounded Knitting Program matrix", () => {
	assert.match(matrices, /key: "program"/)
	assert.match(matrices, /Knitting Program \(Dia × Colour, Kg\)/)
	assert.doesNotMatch(matrices, /requirement/i)
	assert.doesNotMatch(source, /Requirement \(finished cloth/)
})

test("Lot Cloth Program keeps the Dyed Yarn tag on program colours", () => {
	assert.match(source, /section\.key === 'program' &&\s*entry\.dyed_yarn_colours\?\.includes\(colour\)/)
	assert.match(source, /value="Dyed Yarn"/)
})
