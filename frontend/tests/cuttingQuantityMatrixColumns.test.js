import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

import { groupAttributes, itemSections } from "../src/departments/cutting/shared/quantityMatrixLayout.js"

const matrixSource = fs.readFileSync(new URL("../src/departments/cutting/shared/CuttingQuantityMatrix.vue", import.meta.url), "utf8")
const orderTabsSource = fs.readFileSync(new URL("../src/departments/cutting/order/CuttingOrderTabs.vue", import.meta.url), "utf8")
const row = (name, attributes, key) => ({ name, attributes, _row_key: key, values: {} })

test("attribute columns follow the group attribute order", () => {
	assert.deepEqual(groupAttributes({ attributes: ["Colour", "Panel", "Part", "Stage"], pack_attr: "Colour" }), ["Colour", "Panel", "Part", "Stage"])
})

test("attribute columns fall back to pack and set attributes like the Cutting Order view", () => {
	assert.deepEqual(groupAttributes({ pack_attr: "Colour", is_set_item: 1, set_attr: "Part" }), ["Colour", "Part"])
	assert.deepEqual(groupAttributes({ pack_attr: "Colour", is_set_item: 0, set_attr: "Part" }), ["Colour"])
})

test("attribute columns fall back to the first row attributes", () => {
	assert.deepEqual(groupAttributes({ items: [row("Shirt", { Colour: "Red", Part: "Top" }, "a")] }), ["Colour", "Part"])
	assert.deepEqual(groupAttributes({}), [])
})

test("a single-item group yields one section holding every row in backend order", () => {
	const items = [row("Capri", { Colour: "Cream" }, "a"), row("Capri", { Colour: "Almond" }, "b")]
	const sections = itemSections({ items })
	assert.equal(sections.length, 1)
	assert.equal(sections[0].name, "Capri")
	assert.deepEqual(sections[0].rows.map((item) => item._row_key), ["a", "b"])
})

test("a multi-item group yields one section per item in first-appearance order", () => {
	const items = [row("Shirt", {}, "a"), row("Pant", {}, "b"), row("Shirt", {}, "c")]
	const sections = itemSections({ items })
	assert.deepEqual(sections.map((section) => section.name), ["Shirt", "Pant"])
	assert.deepEqual(sections[0].rows.map((item) => item._row_key), ["a", "c"])
	assert.deepEqual(itemSections({ items: [] }), [])
})

test("editor grid renders attribute columns instead of repeated item names and chips", () => {
	assert.doesNotMatch(matrixSource, /Item \/ Attributes/)
	assert.doesNotMatch(matrixSource, /quantity-attribute\b/)
	assert.match(matrixSource, /S\.No\./)
	assert.match(matrixSource, /v-for="attribute in groupAttributes\(group\)"/)
	assert.match(matrixSource, /from "\.\/quantityMatrixLayout\.js"/)
})

test("each item section is its own row group", () => {
	assert.match(matrixSource, /<tbody v-for="\(section, sectionIndex\) in itemSections\(group\)"/)
	assert.match(matrixSource, /scope="rowgroup"/)
})

test("Cutting Order view reuses the shared attribute column helper", () => {
	assert.match(orderTabsSource, /from "\.\.\/shared\/quantityMatrixLayout\.js"/)
	assert.doesNotMatch(orderTabsSource, /function groupAttributes/)
})
