import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { lotTabCount } from "../src/departments/purchase/lot/lotViews.js"

const source = (path) => readFileSync(new URL(`../src/departments/${path}`, import.meta.url), "utf8")

test("Cloth Program is always a tab; writers get Build Cloth Program, readers an empty state", () => {
	const page = source("purchase/lot/LotPage.vue")
	assert.match(page, /<LotEmptyState\s+v-if="!workspace\.permissions\?\.can_write && !workspace\.fabrics\?\.length"/)
	assert.match(page, /<LotFabricTab\s+v-else/)
	assert.match(source("planning/lot/LotPage.vue"), /<LotEmptyState\s+v-if="!workspace\.fabrics\?\.length"/)
})

test("tab badges count Cloth Program routes, Actual Dia conversions and BOM rows only", () => {
	const workspace = { fabrics: [{}, {}], bom: { summary: [{}], additional: [{}, {}] }, order_items: { items: [{}] } }
	assert.equal(lotTabCount(workspace, "fabric"), 2)
	assert.equal(lotTabCount(workspace, "bom"), 3)
	assert.equal(lotTabCount(workspace, "lot"), null)
	assert.equal(lotTabCount({}, "fabric"), 0)
	assert.equal(lotTabCount({ fabrics: [{ conversions: [{}, {}] }, {}], other_conversions: [{}] }, "dia-conversions"), 3)
	assert.equal(lotTabCount({}, "dia-conversions"), 0)
})
