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

test("Lot Cloth Program hides the Process Ledger with its Input/Output rows and moves Actual Dia Conversions to its own tab", () => {
	assert.doesNotMatch(source, /Process Ledger|stepSections|"Input"|Actual Dia Conversions|otherConversions/)
	const conversions = readFileSync(new URL("../src/departments/purchase/lot/LotDiaConversionsTab.vue", import.meta.url), "utf8")
	assert.match(conversions, /<strong>Actual Dia Conversions<\/strong>/)
	assert.match(conversions, /aria-label="Search Actual Dia conversions"/)
	assert.match(conversions, /aria-label="Conversion process"/)
	assert.match(conversions, /lotConversionRows\(\{ fabrics: props\.fabrics, other_conversions: props\.otherConversions \}\)/)
})
