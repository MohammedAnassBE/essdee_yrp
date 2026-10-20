import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const source = (path) => readFileSync(new URL(`../src/departments/sales/${path}`, import.meta.url), "utf8")

test("Production Order quantities are labelled as boxes, matching the Lot and the print format", () => {
	const matrix = source("ProductionOrderMatrix.vue")
	const page = source("ProductionOrder.vue")
	assert.doesNotMatch(matrix, /totalQuantity\) \}\} pcs</)
	assert.match(matrix, /formatNumber\(totalQuantity\) \}\} boxes</)
	assert.doesNotMatch(page, /<small>pieces<\/small>/)
	assert.match(page, /total_quantity\) \}\}<\/strong><small>boxes<\/small>/)
})
