import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"
import { copyDialogSections } from "../src/departments/merch/ipd/ipdCopySections.js"

test("copy labels distinguish attributes, processes and the coupled embellishment copy", () => {
	const rows = copyDialogSections([{ key: "attributes", label: "Item Details", locked: true }, { key: "processes", label: "Item Details", locked: false }])
	assert.deepEqual(rows.map(row => [row.key, row.label, row.note]), [
		["attributes", "Item attributes", "always copied"], ["processes", "Processes", ""],
		["embellishment", "Emblishment", "copied with Processes"],
	])
	assert.equal(rows[2].copyKey, "processes")
	assert.equal(copyDialogSections([{ key: "processes", locked: true }])[1].note, "always copied")
})

test("backend drops embellishment with the optional processes section", () => {
	const source = readFileSync(new URL("../../essdee_yrp/merch/ipd/copy_version.py", import.meta.url), "utf8")
	assert.match(source, /"processes": \{"tables": \("ipd_processes",\), "json": \("emblishment_details_json",\)/)
})
