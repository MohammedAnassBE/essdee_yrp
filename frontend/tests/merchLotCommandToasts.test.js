import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { merchLotCommandSuccess } from "../src/departments/merch/lot/merchLotViews.js"

test("Merch Lot commands have explicit success messages", () => {
	assert.deepEqual(merchLotCommandSuccess("build_cloth_programs", "LOT-1"), { severity: "success", summary: "Cloth Program built", detail: "LOT-1", life: 3500 })
	assert.equal(merchLotCommandSuccess("calculate_bom", "LOT-1").summary, "BOM calculated")
})

test("Merch Lot page toasts only after the command API succeeds", () => {
	const page = readFileSync(new URL("../src/departments/merch/lot/MerchLotPage.vue", import.meta.url), "utf8")
	assert.match(page, /await executeMerchLotCommand[\s\S]*clothVisible.value = false\s*toast.add\(merchLotCommandSuccess\(command, props.lotId\)\)\s*\} catch/)
})
