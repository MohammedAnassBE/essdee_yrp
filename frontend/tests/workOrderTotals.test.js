import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

import { Vue, findNodes, loadComponent, mountComponent } from "../../scripts/helpers/vue_renderer.mjs"
import * as workOrderTotals from "../src/departments/fabric-store/workOrderTotals.js"
import { fabricClothTotal, recutGroupTotals, recutPieces, reworkTotals, sumStageRows } from "../src/departments/fabric-store/workOrderTotals.js"

const matrix = fs.readFileSync(new URL("../src/departments/fabric-store/WorkOrderItemMatrix.vue", import.meta.url), "utf8")
const panel = fs.readFileSync(new URL("../src/departments/fabric-store/WorkOrderActionPanel.vue", import.meta.url), "utf8")

test("Work Order stage totals sum each size and the row total per stage", () => {
	const stage = (key, s, m, total) => ({ key, label: key, values: { S: s, M: m }, total })
	const totals = sumStageRows([
		[stage("planned", 10, 20, 30), stage("delivered", 5, 5, 10), stage("cost", 2, 2, null)],
		[stage("planned", 1.1, 2.2, 3.3), stage("delivered", 0, 1, 1), stage("cost", 9, 9, null)],
	], ["S", "M"])
	assert.deepEqual(totals.map((row) => row.key), ["planned", "delivered"])
	assert.deepEqual(totals[0].values, { S: 11.1, M: 22.2 })
	assert.equal(totals[0].total, 33.3)
	assert.equal(totals[1].total, 11)
})

test("Work Order stage totals never add unit cost but do add total cost", () => {
	const totals = sumStageRows([
		[{ key: "cost", values: { default: 4 }, total: null }, { key: "total_cost", values: { default: 40 }, total: 40 }],
		[{ key: "cost", values: { default: 5 }, total: null }, { key: "total_cost", values: { default: 50.5 }, total: 50.5 }],
	], ["default"])
	assert.deepEqual(totals.map((row) => [row.key, row.total]), [["total_cost", 90.5]])
})

test("Create Rework totals Available and Rework quantity", () => {
	assert.deepEqual(reworkTotals([{ available_qty: 10, qty: 2 }, { available_qty: 5.5, qty: null }]), { available: 15.5, qty: 2 })
})

test("Create Recut totals each size and the recut pieces", () => {
	const group = { items: [{ values: { S: { qty: 2 }, M: { qty: 3 } } }, { values: { S: { qty: 1 }, M: { qty: 0 } } }] }
	assert.deepEqual(recutGroupTotals(group, ["S", "M"]), { values: { S: 3, M: 3 }, total: 6 })
	assert.equal(recutPieces([group, { items: [{ values: { default: { qty: 4 } } }] }]), 10)
})

test("Calculate fabric totals cloth kg across routes with 3 decimals", () => {
	assert.equal(fabricClothTotal({ entries: [{ qty: 0.1 }, { qty: 0.2 }, { qty: null }] }), 0.3)
})

test("Work Order matrix and action popups render a Total footer", () => {
	assert.match(matrix, /<tfoot v-if="section\.items\.length > 1 &&/)
	assert.match(panel, /reworkTotals\(reworkRows\)/)
	assert.match(panel, /recutGroupTotals\(group, primaryValues\(group\)\)/)
	assert.match(panel, /fabricClothTotal\(row\)/)
})

test("Work Order summary matrix footer adds each stage across combinations", () => {
	const Link = { props: ["name"], setup: (props) => () => Vue.h("span", props.name) }
	const Matrix = loadComponent("frontend/src/departments/fabric-store/WorkOrderItemMatrix.vue", { "../../components/common/DocumentLink.vue": Link, "./workOrderTotals.js": workOrderTotals })
	const item = (colour, qty, delivered, received) => ({ name: "Style", attributes: { Colour: colour }, total_qty: qty, total_delivered: delivered, total_received: received, values: { S: { qty, delivered, received } } })
	const root = mountComponent(Matrix, { groups: [{ attributes: ["Colour"], primary_attribute_values: ["S"], items: [item("Red", 20, 15, 10), item("Blue", 7, 6, 1)] }], mode: "summary" })
	const footer = findNodes(root, (node) => node.type === "tfoot")[0]
	const cells = findNodes(footer, (node) => node.type === "td").map((node) => findNodes(node, () => true).map((child) => child.text).join("").trim())
	assert.deepEqual(cells, ["Planned", "27", "27", "Delivered", "21", "21", "Received", "11", "11", "Pending", "10", "10"])
})
