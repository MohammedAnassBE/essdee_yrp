#!/usr/bin/env node

import { existsSync, readFileSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, resolve } from "node:path"

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..")
const dialogPath = resolve(root, "frontend/src/components/documents/RelatedRecordsDialog.vue")
const listPath = resolve(root, "frontend/src/components/common/ListView.vue")
const cuttingSidebarPath = resolve(root, "frontend/src/departments/cutting/CuttingPlanSidebar.vue")
const workOrderRailPath = resolve(root, "frontend/src/departments/fabric-store/WorkOrderActivityRail.vue")
const workOrderPath = resolve(root, "frontend/src/departments/FabricWorkOrder.vue")

function assert(condition, message) {
	if (!condition) throw new Error(message)
}

assert(existsSync(dialogPath), "RelatedRecordsDialog.vue is missing")

const dialog = readFileSync(dialogPath, "utf8")
const list = readFileSync(listPath, "utf8")
const cuttingSidebar = readFileSync(cuttingSidebarPath, "utf8")
const workOrderRail = readFileSync(workOrderRailPath, "utf8")
const workOrder = readFileSync(workOrderPath, "utf8")

for (const contract of [
	'v-model:visible',
	':initial-advanced-filters="filters"',
	':navigation-enabled="false"',
	':allow-bulk-actions="false"',
	'@row-click="openRow"',
	'related-records-dialog--suspended',
]) {
	assert(dialog.includes(contract), `RelatedRecordsDialog omits ${contract}`)
}

assert(list.includes('initialAdvancedFilters'), "ListView has no controlled advanced-filter input")
assert(list.includes('update:advancedFilters'), "ListView does not emit applied advanced filters")
assert(list.includes('v-if="navigationEnabled"'), "ListView cannot suppress page navigation inside a dialog")

assert(cuttingSidebar.includes("RelatedRecordsDialog"), "Cutting related lists do not use the shared dialog")
assert(cuttingSidebar.includes('aria-label="Expand Markers"'), "Marker Expand action is missing")
assert(cuttingSidebar.includes('aria-label="Expand Lay Sheets"'), "Lay Sheet Expand action is missing")
assert(cuttingSidebar.includes("resolvedParentField"), "Cutting expansion does not resolve the parent filter")
assert(cuttingSidebar.includes("reopenExpandedList"), "Cutting record handoff cannot return to the expanded list")
assert(cuttingSidebar.includes(':suspended="markerListSuspended"'), "Marker list state is not retained during record handoff")
assert(cuttingSidebar.includes(':suspended="laySheetListSuspended"'), "Lay Sheet list state is not retained during record handoff")

assert(workOrderRail.includes("RelatedRecordsDialog"), "Work Order related lists do not use the shared dialog")
assert(workOrderRail.includes("Expand ${section.label}"), "Work Order Expand action is missing")
assert(workOrderRail.includes('work_order: props.workOrder'), "Delivery Challan expansion omits its exact Work Order filter")
assert(workOrderRail.includes('against: "YRP Work Order"'), "GRN expansion omits its against filter")
assert(workOrderRail.includes("reopenExpanded"), "Work Order rail does not expose record handoff restoration")
assert(workOrderRail.includes(':suspended="expandedSuspended.delivery_challan"'), "Work Order expanded-list state is not retained during record handoff")
assert(workOrder.includes("activityRail.value?.reopenExpanded"), "Work Order record dialog does not return to its expanded list")

console.log("Related records dialog contract verified.")
