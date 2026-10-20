import assert from "node:assert/strict"
import test from "node:test"
import { lotTabs } from "../src/departments/purchase/lot/lotViews.js"
import { merchLotTabs } from "../src/departments/merch/lot/merchLotViews.js"

test("Purchase keeps empty Cloth Program for writers because Build Cloth Program lives there", () => {
	assert.ok(lotTabs({ permissions: { can_write: true }, fabrics: [], other_conversions: [] }).some(tab => tab.key === "fabric"))
	assert.ok(!lotTabs({ permissions: { can_write: false }, fabrics: [], other_conversions: [] }).some(tab => tab.key === "fabric"))
	for (const values of [{ fabrics: [{}] }, { other_conversions: [{}] }]) {
		assert.ok(lotTabs(values).some(tab => tab.key === "fabric"))
	}
})

test("Merch hides OCR only when loaded data establishes it is empty", () => {
	const hasOcr = workspace => merchLotTabs(workspace).some(tab => tab.key === "ocr")
	assert.equal(hasOcr({}), true)
	assert.equal(hasOcr({ ocr: null }), false)
	assert.equal(hasOcr({ ocr: { processes: {}, total_dispatch: 0 } }), false)
	assert.equal(hasOcr({ ocr: { processes: { Print: {} } } }), true)
	assert.equal(hasOcr({ ocr: { total_dispatch: 5 } }), true)
	assert.deepEqual(merchLotTabs({ ocr: null }).map(tab => tab.key), ["details", "order-items", "order-details", "fabric", "ppo", "bom"])
})
