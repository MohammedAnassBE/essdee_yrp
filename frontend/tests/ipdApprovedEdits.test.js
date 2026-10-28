import assert from "node:assert/strict"
import { readFileSync } from "node:fs"
import test from "node:test"

import { recordActions } from "../src/departments/merch/ipd/ipdEditor.js"
import { lockSavedRows, tableGrid } from "../src/departments/merch/ipd/sections/garmentGrids.js"

const source = (path) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("approved IPD locks saved process rows and leaves new rows editable and removable", () => {
	const grid = lockSavedRows(tableGrid([{ name: "a1", process_name: "Print" }, { process_name: "Wash" }], ["process_name"]))
	assert.deepEqual(grid.rows.map(({ key, readonly, removable }) => ({ key, readonly, removable })), [
		{ key: "a1", readonly: true, removable: false },
		{ key: "new:1", readonly: undefined, removable: undefined },
	])
	assert.deepEqual(grid.model.a1, { process_name: "Print" })
})

test("approved IPD offers the restricted edit only when the server allows it", () => {
	const allowed = { allowed: true, label: "Add processes / panels" }
	const keys = (capabilities) => recordActions({ approved: true, capabilities }).map((action) => action.key)
	assert.deepEqual(keys({ approved_edits: allowed, revert_approval: allowed }), ["edit", "revert_approval"])
	assert.deepEqual(keys({ approved_edits: { allowed: false }, revert_approval: allowed }), ["revert_approval"])
	assert.equal(recordActions({ approved: true, capabilities: { approved_edits: allowed } })[0].label, "Add processes / panels")
})

test("restricted editor opens only the process add action and embellishment panels", () => {
	const section = source("departments/merch/ipd/sections/IpdProcessesSection.vue")
	assert.match(section, /label="Add process"/)
	assert.match(section, /part === 'general' && \(!editor\.readonly \|\| editor\.approvedEdits\)" label="Add process"/)
	assert.match(section, /editor\.approvedEdits \? lockSavedRows\(grid\) : grid/)
	assert.match(section, /:model-value="embellishment\.model"\n\t+:readonly="editor\.readonly && !editor\.approvedEdits"/)
	assert.match(section, /<div v-if="!editor\.readonly" class="ipd-inline-add">/)
	const editor = source("departments/merch/ipd/useIpdEditor.js")
	assert.match(editor, /readonly: approvedEdits, approvedEdits/)
	assert.match(source("components/common/EntryGrid.vue"), /:disabled="row\.removable === false"/)
	assert.match(source("components/common/EntryGrid.vue"), /props\.rows\.filter\(\(row\) => row\.removable !== false\)/)
})
