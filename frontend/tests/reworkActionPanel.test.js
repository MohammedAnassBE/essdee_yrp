import assert from "node:assert/strict"
import fs from "node:fs"
import test from "node:test"

const panel = fs.readFileSync(new URL("../src/departments/fabric-store/WorkOrderActionPanel.vue", import.meta.url), "utf8")
const grnWorkspace = fs.readFileSync(new URL("../src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue", import.meta.url), "utf8")

test("Create Rework says why it has no rows instead of showing an empty table", () => {
	assert.match(panel, /<Message v-if="!reworkRows\.length && !error"[^>]*>No rework items\./)
	assert.match(panel, /<div v-else class="work-order-action-panel__table-wrap"[^>]*aria-label="Rework quantities"/)
})

test("rework stock context lists each received type once", () => {
	const source = panel.match(/function reworkContext\(row\) \{([^\n]+)\}/)?.[1]
	assert.ok(source)
	const reworkContext = new Function("row", source)
	assert.equal(reworkContext({ role: "Rework", received_type: "Printing Mistake", dimensions: { lot: "LX1", received_type: "Printing Mistake" } }), "Rework · Printing Mistake · LX1")
})

test("a draft GRN can tick Allow Non Bundle like Desk", () => {
	const owned = grnWorkspace.match(/const sourceOwnedFieldnames = new Set\(\[([^\]]+)\]\)/)?.[1]
	assert.ok(owned)
	assert.doesNotMatch(owned, /allow_non_bundle/)
	assert.match(grnWorkspace, /source\.fieldname === "allow_non_bundle" && cutPanelMovementOwned\.value/)
	assert.match(grnWorkspace, /const cutPanelMovementOwned = computed\(\(\) => Boolean\(form\.cut_panel_movement \|\| workspace\.value\.record\?\.cut_panel_movement\)\)/)
})
