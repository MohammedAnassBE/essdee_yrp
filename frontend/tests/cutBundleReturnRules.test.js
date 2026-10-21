import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { collapsedPanelSummary, collapsedStockMessage } from "../src/departments/fabric-store/collapsedStock.js"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const panels = [{ panel: "Sleeve", colour: "Green", size: "S", quantity: 8 }]

test("collapsed stock notice asks for Allow Non Bundle until it is ticked", () => {
	assert.equal(collapsedPanelSummary(panels), "Sleeve / Green / S: 8")
	const blocked = collapsedStockMessage({ panels, lot: "LOT-1", location: "S-1", doctypeLabel: "Delivery Challan" })
	assert.match(blocked, /^Lot LOT-1 cut panels at S-1 are collapsed stock \(Sleeve \/ Green \/ S: 8\)\. Tick Allow Non Bundle/)
	assert.match(blocked, /Moving them as exact bundles is blocked\.$/)
	const ticked = collapsedStockMessage({ panels, lot: "LOT-1", location: "S-1", allowNonBundle: true, doctypeLabel: "Delivery Challan" })
	assert.match(ticked, /Allow Non Bundle is ticked, so this Delivery Challan moves them by quantity\.$/)
	assert.equal(collapsedStockMessage({ panels: [], lot: "LOT-1", location: "S-1" }), "")
})

test("GRN notice does not claim to auto-tick", () => {
	const message = collapsedStockMessage({ panels, lot: "L", location: "S", doctypeLabel: "Goods Received Note", autoTick: false })
	assert.match(message, /If this Goods Received Note moves these panels, tick Allow Non Bundle/)
})

test("DC auto-ticks Allow Non Bundle for collapsed source stock; GRN only explains it", () => {
	const dc = read("departments/fabric-store/DeliveryChallanWorkspace.vue")
	assert.match(dc, /location: \(\) => form\.from_location,/)
	assert.match(dc, /autoTick: true,/)
	assert.match(dc, /class="collapsed-stock-notice"/)
	const grn = read("departments/fabric-store/GoodsReceivedNoteWorkspace.vue")
	assert.match(grn, /location: \(\) => form\.supplier,/)
	assert.match(grn, /enabled: \(\) => canEditDraft\.value && !Number\(form\.is_return \|\| 0\)/)
	assert.match(grn, /autoTick: false,/)
})

test("whole-bundle return prefills and locks the CPM panels and explains collapsed returns", () => {
	const panel = read("departments/fabric-store/DeliveryChallanReturnPanel.vue")
	assert.match(panel, /getDeliveryChallanReturnMovement\(props\.context\.delivery_challan, movement\)/)
	assert.match(panel, /:disabled="Boolean\(acting\) \|\| isLocked\(row\)"/)
	assert.match(panel, /cutPanelMovement\.value && movementRows\.value && !movementError\.value/)
	assert.match(panel, /Typed panel quantities come back as collapsed stock/)
	assert.match(panel, /is filled in and locked/)
	assert.match(panel, /const request = \+\+movementRequest\n\tmovementError\.value = ""\n\tloadingMovement\.value = false/)
})
