import assert from "node:assert/strict"
import test from "node:test"
import { readFileSync } from "node:fs"

import { lotChoicesForEntry, lotNamesInOptions } from "../src/departments/fabric-store/grnLotOptions.js"

const lotOptions = { "PO-ROW-1": ["LOT-1", "LOT-2"], "PO-ROW-2": ["LOT-2", "LOT-3"] }

test("GRN lot choices describe each Lot by its Item", () => {
	const entry = { ref_docname: "PO-ROW-1", dimensions: { lot: "OLD-LOT" } }
	assert.deepEqual(lotChoicesForEntry(entry, lotOptions, "lot", { "LOT-1": "Maze Capri", "OLD-LOT": "Tank Top" }), [
		{ label: "LOT-1", value: "LOT-1", description: "Maze Capri", disabled: false },
		{ label: "LOT-2", value: "LOT-2", description: "", disabled: false },
		{ label: "OLD-LOT", value: "OLD-LOT", description: "Tank Top", disabled: true },
	])
})

test("GRN lot names are collected once across Purchase Order rows", () => {
	assert.deepEqual(lotNamesInOptions(lotOptions), ["LOT-1", "LOT-2", "LOT-3"])
	assert.deepEqual(lotNamesInOptions(undefined), [])
})

test("GRN lot select renders the Item line and searches it", () => {
	const source = readFileSync(new URL("../src/departments/fabric-store/GoodsReceivedNoteWorkspace.vue", import.meta.url), "utf8")
	assert.match(source, /lotChoicesForEntry\(row, workspace\.lot_options, lotFieldname, lotItems\)/)
	assert.match(source, /:filter-fields="\['label', 'description'\]"/)
	assert.match(source, /<small v-if="option\.description">\{\{ option\.description \}\}<\/small>/)
	assert.match(source, /getList\("SD YRP Lot", \{ fields: \["name", "item"\]/)
})
