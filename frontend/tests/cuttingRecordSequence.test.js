import assert from "node:assert/strict"
import test from "node:test"
import fs from "node:fs"

import { adjacentRecordNames, listSnapshotNames } from "../src/departments/cutting/recordSequence.js"

const read = (path) => fs.readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8")

test("adjacent record names follow the list order and stop at the ends", () => {
	const names = ["CLS-3", "CLS-1", "CLS-2"]
	assert.deepEqual(adjacentRecordNames(names, "CLS-3"), { previousName: "", nextName: "CLS-1" })
	assert.deepEqual(adjacentRecordNames(names, "CLS-1"), { previousName: "CLS-3", nextName: "CLS-2" })
	assert.deepEqual(adjacentRecordNames(names, "CLS-2"), { previousName: "CLS-1", nextName: "" })
	assert.deepEqual(adjacentRecordNames(names, "CLS-9"), { previousName: "", nextName: "" })
	assert.deepEqual(adjacentRecordNames(names, ""), { previousName: "", nextName: "" })
})

test("expanded list sequence reuses the popup filters and order", async () => {
	const calls = []
	const snapshot = { doctype: "SD YRP Cutting LaySheet", filters: [["cutting_plan", "=", "CP-1"]], orderBy: "lay_no asc, name asc", total: 3 }
	const names = await listSnapshotNames(snapshot, async (doctype, options) => {
		calls.push([doctype, options])
		return [{ name: "CLS-1" }, { name: "CLS-2" }]
	})
	assert.deepEqual(names, ["CLS-1", "CLS-2"])
	assert.equal(calls[0][0], "SD YRP Cutting LaySheet")
	assert.deepEqual(calls[0][1].filters, snapshot.filters)
	assert.equal(calls[0][1].orderBy, "lay_no asc, name asc")
	assert.equal(calls[0][1].start, 0)
	assert.ok(calls[0][1].pageLength >= 3)
})

test("cutting plan rail and expanded popups pass their list order to the record dialogs", () => {
	const sidebar = read("departments/cutting/CuttingPlanSidebar.vue")
	assert.match(sidebar, /openMarker\(marker\.name, filteredMarkers\)/)
	assert.match(sidebar, /openLaySheet\(sheet\.name, filteredLaySheets\)/)
	assert.match(sidebar, /loadExpandedSequence\(markerSequence, snapshot\)/)
	assert.match(sidebar, /loadExpandedSequence\(laySheetSequence, snapshot\)/)
	assert.match(sidebar, /@navigate="selectedMarker = \$event"/)
	assert.match(sidebar, /@navigate="selectedLaySheet = \$event"/)
	const related = read("components/documents/RelatedRecordsDialog.vue")
	assert.match(related, /emit\("open", row, snapshot\)/)
	assert.match(related, /\.related-records-dialog \.list-title-block \{\s*display: none;/)
	assert.match(related, /\.related-records-dialog__body \{[^}]*padding: 0 20px 16px;/)
	const listView = read("components/common/ListView.vue")
	assert.match(listView, /function navigationSnapshot\(row\) \{\n\tif \(!route\.name\) return null/)
	for (const dialog of ["CuttingMarkerDialog.vue", "CuttingLaySheetDialog.vue"]) {
		const source = read(`departments/cutting/${dialog}`)
		assert.match(source, /<RecordDialogHeader[\s\S]*?@navigate="emit\('navigate', \$event\)"/)
	}
	assert.match(read("departments/cutting/CuttingMarkerDialog.vue"), /:disabled="loading \|\| saving \|\| editingExisting"/)
	assert.match(read("components/navigation/InlinePageNavigation.vue"), /<DocumentStepButtons/)
})
