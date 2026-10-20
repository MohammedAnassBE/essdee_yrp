import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"
import { computed, ref } from "vue"

function setup(payload) {
	const source = fs.readFileSync(new URL("../src/departments/sewing/reports/SewingStatusSummary.vue", import.meta.url), "utf8")
		.split("<script setup>")[1].split("</script>")[0].replace(/^import .*$/gm, "")
	const filters = { lot: [], item: [], colour: [], part: [], fromDate: "", toDate: "" }
	return new Function("defineProps", "useSewingContext", "ref", "computed", "watch", "onBeforeUnmount", "getSewingStatusSummary",
		`${source}\ndata.value = arguments[7]; return { columns, visible, totals, filters: props.filters }`)(
		() => ({ filters }), () => ({ supplier: ref("S-0172"), beginRequest() {}, isCurrent() { return true } }),
		ref, computed, () => {}, () => {}, () => {}, payload,
	)
}

test("Status Summary resolves Work Order Status from the API field while keeping blank readiness", () => {
	const state = setup({
		header1: ["Item", "SD YRP Lot", "Colour", "Part"], header2: ["Order Qty"],
		header3: ["Ready for Checking", "Work Order Status"],
		data: [{ is_total: true }, { item: "Shirt", lot: "L1", colour: "Blue", part: "", "Order Qty": 10, "Ready for Checking": "", work_order_status: "Open" }],
	})
	const cells = Object.fromEntries(state.columns.value.map(column => [column.label, state.visible.value[0][column.key]]))
	assert.equal(cells["Work Order Status"], "Open")
	assert.equal(cells["Ready for Checking"], "")
	assert.equal(cells.Item, "Shirt")
	assert.equal(cells["SD YRP Lot"], "L1")
	assert.equal(cells["Order Qty"], 10)
})

test("Status Summary preserves readiness and authoritative quantities while filtering lots", () => {
	const state = setup({
		header1: ["Item", "SD YRP Lot"], header2: ["Order Qty"], header3: ["Ready for AQL", "Work Order Status"],
		data: [{ is_total: true },
			{ item: "Shirt", lot: "L1", "Order Qty": 10, "Ready for AQL": "", work_order_status: "Open" },
			{ item: "Shirt", lot: "L2", "Order Qty": 20, "Ready for AQL": "Under AQL", work_order_status: "Open" }],
	})
	state.filters.lot = ["L2"]
	assert.equal(state.visible.value.length, 1)
	assert.equal(state.visible.value[0]["Ready for AQL"], "Under AQL")
	assert.equal(state.totals.value["Order Qty"], 20)
})
