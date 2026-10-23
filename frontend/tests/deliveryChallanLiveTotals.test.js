import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { deliveredQuantity, rowTotal } from "../src/engine/stock/deliveryChallanTotals.js"
import { Vue } from "../../scripts/helpers/vue_renderer.mjs"

test("F-B16 delivered quantity sums live cells across delivery and correction blocks", () => {
	const row = { values: { S: { qty: "2.5", secondary_qty: 100 }, M: { qty: 3 }, L: null } }
	const blocks = [{ groups: [{ items: [row, { values: { default: { qty: 4 } } }] }, {}] }, { groups: [{ items: [{ values: { default: { qty: 1.25 } } }] }] }, {}]
	assert.equal(rowTotal(row), 5.5)
	assert.equal(deliveredQuantity(blocks), 10.75)
	row.values.S.qty = 7
	assert.equal(deliveredQuantity(blocks), 15.25)
	assert.equal(deliveredQuantity([]), 0)
	assert.equal(deliveredQuantity(), 0)
})

test("F-B16 rail uses live quantities and additional value while server values wait for save", () => {
	const source = readFileSync(new URL("../src/departments/fabric-store/DeliveryChallanWorkspace.vue", import.meta.url), "utf8")
	const expression = source.match(/const visibleTotals = computed\(([\s\S]*?)\nconst canEditDraft/)[1]
	const totals = [
		{ fieldname: "total_delivered_qty", value: 99 }, { fieldname: "additional_goods_value", value: 0 },
		{ fieldname: "stock_value", value: 120 }, { fieldname: "total_value", value: 120 },
	]
	const workspace = Vue.ref({ totals }), canEdit = Vue.ref(true), form = Vue.reactive({ additional_goods_value: 40 })
	const matrixBlocks = Vue.ref([{ groups: [{ items: [{ values: { default: { qty: 5 } } }] }] }])
	const totalIsPositive = total => Number(total.value || 0) > 0
	const primaryTotals = new Set(["total_delivered_qty", "stock_value", "total_value"])
	const visible = new Function("computed", "workspace", "canEdit", "form", "matrixBlocks", "deliveredQuantity", "primaryTotals", "totalIsPositive", `return computed(${expression}`)(Vue.computed, workspace, canEdit, form, matrixBlocks, deliveredQuantity, primaryTotals, totalIsPositive)
	assert.deepEqual(visible.value.map(total => total.value), [5, 40, 120, 120])
	matrixBlocks.value[0].groups[0].items[0].values.default.qty = 8
	form.additional_goods_value = 60
	assert.deepEqual(visible.value.map(total => total.value), [8, 60, 120, 120])
	canEdit.value = false
	assert.deepEqual(visible.value.map(total => total.value), [99, 120, 120])
	assert.match(source, /dirty && serverValueTotals\.has\(total.fieldname\)/)
	assert.match(source, /const serverValueTotals = new Set\(\["stock_value", "total_value"\]\)/)
	assert.match(source, />Updates on save<\/small>/)
	assert.match(source, /import \{ deliveredQuantity, getTableTotals, isTableFilled, pendingQuantity, rowTotal, setTableQuantities \}/)
})
