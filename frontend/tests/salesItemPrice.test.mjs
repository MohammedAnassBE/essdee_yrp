import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { DEFAULT_RATE_TYPE, changedPrices, groupBySizes, isPriceEditable } from "../src/departments/sales/salesItemPrices.js"
import { departments, getWorkspacePaths } from "../src/departments/registry.js"

const source = (path) => readFileSync(new URL(path, import.meta.url), "utf8")
const item = (name, sizes, mrp = {}) => ({
	item: name, item_name: name, sizes, missing: [],
	variants: Object.fromEntries(sizes.map((size) => [size, `${name}-${size}`])),
	prices: { mrp_rate: { ...Object.fromEntries(sizes.map((size) => [size, 0])), ...mrp }, rate: {}, retail_rate: {} },
})

test("MRP Rate is the default rate type", () => {
	assert.equal(DEFAULT_RATE_TYPE, "mrp_rate")
})

test("items with the same sizes share one table, in first-seen order", () => {
	const groups = groupBySizes([item("A", ["S", "M"]), item("B", ["28", "30"]), item("C", ["S", "M"])])
	assert.deepEqual(groups.map((group) => [group.sizes, group.items.map((row) => row.item)]), [[["S", "M"], ["A", "C"]], [["28", "30"], ["B"]]])
})

test("changed prices map each edited variant of the chosen rate type to its new rate", () => {
	const original = [item("A", ["S", "M"], { S: 100 })]
	const edited = structuredClone(original)
	edited[0].prices.mrp_rate.M = 120
	edited[0].prices.rate.S = 90
	assert.deepEqual(changedPrices(original, edited, "mrp_rate"), { "A-M": 120 })
	assert.deepEqual(changedPrices(original, edited, "rate"), { "A-S": 90 })
	assert.deepEqual(changedPrices(original, original, "mrp_rate"), {})
})

test("prices are editable only for one selected item with write permission", () => {
	assert.equal(isPriceEditable("", { can_write: true }), false)
	assert.equal(isPriceEditable("Tee", { can_write: false }), false)
	assert.equal(isPriceEditable("Tee", { can_write: true }), true)
})

test("Sales shows a Sales Item Price card and route in the Sales layout", () => {
	const sales = departments.find((department) => department.key === "sales")
	assert.deepEqual(getWorkspacePaths(sales).item_prices, ["/sales/item-prices"])
	assert.match(source("../src/departments/sales/SalesLauncher.vue"), /key: "item_prices",\s*label: "Sales Item Price"[\s\S]*to: "\/sales\/item-prices"/)
	assert.match(source("../src/router/index.js"), /path: "\/sales\/item-prices", name: "sales-item-prices", component: SalesItemPricePage/)
	const layout = JSON.parse(source("../../essdee_yrp/fixtures/yrp_ui_layout.json")).find((row) => row.experience_key === "sales")
	assert.deepEqual(JSON.parse(layout.config).experience_props.workspaces, ["production_orders", "item_prices", "reports"])
})

test("the page labels the per-piece rate and saves through the essdee_yrp API", () => {
	const page = source("../src/departments/sales/SalesItemPrice.vue")
	assert.match(page, /label="Rate Type"/)
	assert.match(page, /UOM/)
	const api = source("../src/api/sales.js")
	assert.match(api, /essdee_yrp\.sales\.item_prices\.get_item_price_grid/)
	assert.match(api, /essdee_yrp\.sales\.item_prices\.save_item_prices/)
})
