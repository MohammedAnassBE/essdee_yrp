import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { canCreateDc, isExistingDc, prefilledEntry } from "../src/departments/finishing/plan/finishingSourceEntries.js"

const read = (file) => readFileSync(new URL(`../src/departments/finishing/${file}`, import.meta.url), "utf8")
const payload = {
	primary_values: ["S", "M", "L"],
	data: { data: { Blue: { check_value: true }, Red: { check_value: true } } },
}

test("Create DC shows only for entries without a DC when entries can be created", () => {
	assert.equal(canCreateDc({ name: "SE-1", dc: "" }, true), true)
	assert.equal(canCreateDc({ name: "SE-1" }, true), true)
	assert.equal(canCreateDc({ name: "SE-1", dc: "" }, false), false)
	assert.equal(canCreateDc({ name: "SE-1", dc: "DC-1" }, true), false)
	assert.equal(canCreateDc({ name: "SE-1", dc: "existing" }, true), false)
	assert.equal(isExistingDc({ dc: "existing" }), true)
	assert.equal(isExistingDc({ dc: "DC-1" }), false)
})

test("prefill fills the entry quantities and checks only its colours", () => {
	const entry = prefilledEntry(payload, { Blue: { M: 3, L: "2" } })
	assert.deepEqual(entry, {
		Blue: { checked: true, sizes: { S: 0, M: 3, L: 2 } },
		Red: { checked: false, sizes: { S: 0, M: 0, L: 0 } },
	})
})

test("source entry rows switch from the button to the DC link once a DC exists", () => {
	const source = read("plan/FinishingSourceEntries.vue")
	assert.match(source, /<Button v-if="canCreateDc\(entry, canCreate\)" label="Create DC"[^>]*@click="emit\('create-dc', entry\)"/)
	assert.match(source, /v-else-if="entry\.dc"[^>]*@click="emit\('open', 'YRP Delivery Challan', entry\.dc\)">\{\{ entry\.dc \}\}/)
})

test("Ironing Excess and Old Lot tabs open the shared Create DC dialog with the entry prefill", () => {
	const tabs = read("FinishingPlanTabs.vue")
	assert.match(tabs, /value: "old-lot"[^\n]*sourceEntries:/)
	assert.match(tabs, /value: "ironing-excess"[^\n]*sourceEntries:/)
	assert.match(tabs, /emit\("entry", "create_delivery_challan", \{ prefill: sourceEntry\.quantities, sourceEntry: sourceEntry\.name \}\)/)
	const plan = read("FinishingPlan.vue")
	assert.match(plan, /<FinishingEntryDialog[^>]*:prefill="entryContext\.prefill" :source-entry="entryContext\.sourceEntry"/)
	assert.match(plan, /function openEntry\(action, context = \{\}\) \{\n\tentryAction\.value = action\n\tentryContext\.value = context/)
	const dialog = read("FinishingEntryDialog.vue")
	assert.match(dialog, /props\.prefill \? prefilledEntry\(source\.value, props\.prefill\) : initialEntry\(source\.value\)/)
	assert.match(dialog, /props\.sourceEntry \? \{ \.\.\.payload, source_entry: props\.sourceEntry \} : payload/)
})
