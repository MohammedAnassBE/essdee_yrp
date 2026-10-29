import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"
import { nextTick, ref } from "vue"

import { useRowSelection } from "../src/components/common/childGrid/rowSelection.js"

const read = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")
const templateOf = (source) => source.slice(0, source.indexOf("<script setup>"))

const entryGridTables = {
	"departments/merch/ipd/cloth/IpdCompactingSection.vue": ['@remove-row="compacting.remove"'],
	"departments/merch/ipd/cloth/IpdFabricProcessesSection.vue": ['@remove-row="removeProcessRow"', '@remove-row="mappings.remove"'],
	"departments/merch/ipd/cloth/IpdFabricRoutesSection.vue": ['@remove-row="routes.remove"'],
	"departments/merch/ipd/cloth/IpdYarnRatioSection.vue": ['@remove-row="ratios.remove"'],
	"departments/merch/ipd/sections/IpdAccessoriesSection.vue": ['@remove-row="removeBom"', '@remove-row="removeAccessory"'],
	"departments/merch/ipd/sections/IpdCuttingSection.vue": ['@remove-row="removeCloth"'],
	"departments/merch/ipd/sections/IpdProcessesSection.vue": ['@remove-row="removeProcess"', '@remove-row="removeEmbellishmentProcess"'],
	"departments/merch/ipd/sections/IpdStitchingSection.vue": ['@remove-row="togglePanel($event, false)"', '@remove-row="removeGroup"'],
	"departments/merch/process-cost/ProcessCostGrid.vue": ['@remove-row="removeRow"'],
}

test("EntryGrid deletes through a checkbox column and a selection footer, not a row button", () => {
	const template = templateOf(read("components/common/EntryGrid.vue"))
	assert.match(template, /data-row-select tabindex="-1" :checked="rowSelection\.isSelected\(row\.key\)" :disabled="row\.removable === false"/)
	assert.match(template, /:indeterminate="rowSelection\.isPartlySelected\.value"/)
	assert.match(template, /<footer v-if="rowSelection\.selected\.value\.length"/)
	assert.doesNotMatch(template, /pi-times|aria-label="`Remove/)
})

test("IPD and process cost child tables remove rows only through EntryGrid selection", () => {
	for (const [path, handlers] of Object.entries(entryGridTables)) {
		const template = templateOf(read(path))
		assert.doesNotMatch(template, /<Button[^>]*pi-trash/, path)
		for (const handler of handlers) assert.ok(template.includes(handler), `${path} keeps ${handler}`)
		assert.ok(template.includes(":removable-rows="), path)
	}
})

test("approved IPD processes keep saved rows locked while allowing new rows", () => {
	const template = templateOf(read("departments/merch/ipd/sections/IpdProcessesSection.vue"))
	assert.ok(template.includes(':removable-rows="!editor.readonly || editor.approvedEdits"'))
	assert.match(read("departments/merch/ipd/sections/garmentGrids.js"), /row\.key\.startsWith\("new:"\) \? row : \{ \.\.\.row, readonly: true, removable: false \}/)
})

test("process cost delete stops once one tier is left", async () => {
	const tiers = ref(["t0", "t1", "t2"])
	const keys = () => tiers.value.length > 1 ? tiers.value.map((_, index) => `tier-${index}`) : []
	const selection = useRowSelection(keys)
	selection.toggleAll(true)
	await selection.removeSelected((key) => { tiers.value = tiers.value.filter((_, index) => `tier-${index}` !== key) }, () => tiers.value.length > 1)
	await nextTick()
	assert.deepEqual(tiers.value, ["t0"])
	assert.ok(templateOf(read("departments/merch/process-cost/ProcessCostGrid.vue")).includes(':removable-rows="!readonly && tiers.length > 1"'))
})
