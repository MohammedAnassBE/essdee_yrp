import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("GRN overview shows Allow Non Bundle", () => {
	const status = read("departments/fabric-store/GoodsReceivedNoteWorkspace.vue").split("\n").find((line) => line.includes('{ key: "status"'))
	assert.ok(status.includes('"allow_non_bundle"'))
})

test("Submitting a Cut Panel Movement keeps the dialog open for the next transaction", () => {
	const dialog = read("departments/cut-panel-store/CutPanelMovementDialog.vue")
	assert.match(dialog, /if \(command === "cancel"\) emit\("update:visible", false\)\n\t\telse await loadLinked\(\)/)
	assert.doesNotMatch(dialog, /command === "submit"\) emit\("update:visible", false\)/)
	assert.match(dialog, /document-label="Cut Panel Movement"/)
})


test("Cut Panel Store movement can come from a Cutting Plan so its accessory foldings list", () => {
	const dialog = read("departments/cut-panel-store/CutPanelMovementDialog.vue")
	assert.match(dialog, /<ToggleSwitch v-model="form\.movement_from_cutting" :disabled="Boolean\(record\) \|\| busy" @update:model-value="sourceChanged" \/>/)
	assert.match(dialog, /<LinkField v-if="form\.movement_from_cutting" v-model="form\.cutting_plan" doctype="SD YRP Cutting Plan" label="Cutting Plan" required :filters="cuttingPlanFilters"/)
	assert.match(dialog, /const cuttingPlanFilters = computed\(\(\) => \(\{ lot: form\.lot, docstatus: 1, version: \["!=", "V1"\] \}\)\)/)
	assert.match(dialog, /movement_from_cutting: false, cutting_plan: ""/)
})
