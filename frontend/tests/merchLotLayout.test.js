import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { LOT_TABS, hasLotOcr, lotEditorTabs, resolveLotTab } from "../src/departments/purchase/lot/lotLayout.js"

const source = (path) => readFileSync(new URL(`../src/departments/merch/lot/${path}`, import.meta.url), "utf8")

test("OCR section shows only when loaded data has processes or dispatch", () => {
	assert.equal(hasLotOcr(null), false)
	assert.equal(hasLotOcr({ processes: {}, total_dispatch: 0 }), false)
	assert.equal(hasLotOcr({ processes: { Print: {} } }), true)
	assert.equal(hasLotOcr({ total_dispatch: 5 }), true)
})

test("Merch legacy tab links land on the Lot tab with the matching section", () => {
	assert.deepEqual(resolveLotTab("ppo"), { tab: "lot", section: "ppo" })
	assert.deepEqual(resolveLotTab("ocr"), { tab: "lot", section: "ocr" })
	assert.deepEqual(resolveLotTab("bom"), { tab: "bom", section: "" })
	assert.deepEqual(resolveLotTab("fabric", lotEditorTabs(true)), { tab: "lot", section: "" })
})

test("Merch Lot page and editor use the shared four-tab Lot layout", () => {
	const page = source("MerchLotPage.vue")
	assert.match(page, /<LotViewMain\b/)
	assert.match(page, /useLotLayout\(LOT_TABS, /)
	assert.match(page, /<LotBomPanel\b/)
	assert.doesNotMatch(page, /value="(details|order-items|order-details|ppo|ocr)"/)
	const editor = source("MerchLotEditor.vue")
	assert.match(editor, /<LotEditorMain\b/)
	assert.match(editor, /<template #quantities>\s*<LotOrderItemsEditor[^>]*:box-locked="locks.box_locked"/)
	const composable = source("useMerchLotEditor.js")
	assert.match(composable, /lotEditorTabs\(isNew\)/)
	assert.match(composable, /useLotTabWorkspace\(lotId, activeTab, getMerchLotWorkspace\)/)
	assert.doesNotMatch(composable, /activeTab\.value = "(order-items|details)"/)
	assert.deepEqual(LOT_TABS.map((tab) => tab.key), ["lot", "fabric", "dia-conversions", "bom"])
	for (const file of [page, editor]) assert.match(file, /<TabPanel v-else-if="activeTab === 'dia-conversions'" value="dia-conversions">\s*<LotDiaConversionsTab /)
})
