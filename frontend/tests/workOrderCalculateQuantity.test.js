import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

const panel = fs.readFileSync(new URL("../src/departments/fabric-store/WorkOrderActionPanel.vue", import.meta.url), "utf8")
const desk = fs.readFileSync(new URL("../../essdee_yrp/public/js/work_order.js", import.meta.url), "utf8")

test("/web Calculate accepts any garment quantity without capping it to the Lot quantity", () => {
	const input = panel.match(/<InputNumber v-model="row\.values\[value\]\.qty"[^>]*\/>/)?.[0]
	assert.ok(input)
	assert.doesNotMatch(input, /:max=/)
	assert.match(panel, /cell\?\.source_row && Number\(cell\.qty \|\| 0\) > 0\)\.map\(\(cell\) => \(\{ source_row: cell\.source_row, qty: Number\(cell\.qty\) \}\)\)/)
})

test("Desk Calculate Items accepts any quantity and reselecting restores the Lot quantity", () => {
	const input = desk.match(/<input class="form-control input-sm essdee-wo-calc-qty"[^>]*>/)?.[0]
	assert.ok(input)
	assert.doesNotMatch(input, /\bmax=/)
	assert.match(input, /step="any"/)
	assert.match(desk, /\$\(this\)\.val\(selected \? \$\(this\)\.data\("lot-qty"\) : 0\);/)
	assert.doesNotMatch(desk, /attr\("max"\)/)
})
