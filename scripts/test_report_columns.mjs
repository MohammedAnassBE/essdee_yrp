#!/usr/bin/env node

import assert from "node:assert/strict"

import { getLinkedValues } from "../frontend/src/api/webReports.js"
import {
	buildLinkedValueBatches,
	cellAlign,
	createHydrationLifecycle,
	getLayoutColumnsForSave,
	hydrateLinkedValueBatches,
	linkSourceLabel,
	normalizeReportRows,
	reconcileReportLayout,
	reportCellValue,
} from "../frontend/src/composables/reportColumns.js"

const baseColumns = [
	{ fieldname: "item", fieldtype: "Link", label: "Item", options: "Item", width: 140 },
	{ fieldname: "qty", fieldtype: "Float", label: "Quantity" },
	{ fieldname: "warehouse", fieldtype: "Link", label: "Warehouse", options: "Warehouse" },
]
const savedLayout = [
	{ column_key: "base:qty", kind: "base", visible: 1, align: "left", width: 90 },
	{
		column_key: "linked:item:item_group",
		kind: "linked",
		source_column: "item",
		target_field: "item_group",
		visible: 1,
		align: "center",
		width: 180,
	},
	{ column_key: "base:removed", kind: "base", visible: 1, align: "auto", width: 100 },
	{ column_key: "base:item", kind: "base", visible: 0, align: "auto", width: 140 },
]
const fieldsBySource = {
	item: [{ fieldname: "item_group", fieldtype: "Link", label: "Item Group", options: "Item Group" }],
}
const reconciled = reconcileReportLayout(baseColumns, savedLayout, fieldsBySource)
assert.deepEqual(reconciled.map((column) => column.key), [
	"base:qty",
	"linked:item:item_group",
	"base:item",
	"base:warehouse",
])
assert.equal(reconciled[0].align, "left")
assert.equal(reconciled[0].width, 90)
assert.equal(reconciled[1].label, "Item · Item Group")
assert.equal(reconciled[2].visible, false)
assert.equal(reconciled[3].visible, true)

assert.equal(cellAlign(reconciled[0]), "report-align-left")
assert.equal(cellAlign({ fieldtype: "Currency", align: "auto" }), "report-align-right")
assert.equal(cellAlign({ fieldtype: "Data", align: "auto" }), "report-align-left")
assert.equal(cellAlign({ fieldtype: "Float", align: "center" }), "report-align-center")
assert.equal(linkSourceLabel({ doctype: "Item", label: "Item Variant" }), "Item (Item Variant)")
assert.equal(linkSourceLabel({ doctype: "Supplier", label: "Supplier" }), "Supplier")

const hiddenLinkedColumns = Array.from({ length: 20 }, (_value, index) => ({
	key: `linked:item:hidden_${index}`,
	kind: "linked",
	source_column: "item",
	target_field: `hidden_${index}`,
	visible: false,
}))
const visibleLinkedColumn = {
	key: "linked:item:item_group",
	kind: "linked",
	source_column: "item",
	target_field: "item_group",
	visible: true,
}
const savedColumns = getLayoutColumnsForSave([baseColumns[0], ...hiddenLinkedColumns, visibleLinkedColumn])
assert.equal(savedColumns.filter((column) => column.kind === "linked").length, 1)
assert.equal(savedColumns.some((column) => column.target_field === "hidden_0"), false)
assert.throws(
	() => getLayoutColumnsForSave(Array.from({ length: 21 }, (_value, index) => ({
		...visibleLinkedColumn,
		key: `linked:item:visible_${index}`,
		target_field: `visible_${index}`,
	}))),
	/You can select up to 20 linked fields/,
)

const rows = normalizeReportRows([
	{ item: "ITEM-1", qty: 3 },
	["Total", 3, null],
], baseColumns)
assert.equal(rows[0].is_total_row, undefined)
assert.equal(rows[1].item, "Total")
assert.equal(rows[1].qty, 3)
assert.equal(rows[1].is_total_row, true)
assert.deepEqual(normalizeReportRows({ report_data: [] }, baseColumns), [])

const hydrated = {
	item: { "ITEM-1": { item_group: "Products" } },
}
assert.equal(reportCellValue(rows[0], reconciled[1], hydrated), "Products")
assert.equal(reportCellValue(rows[1], reconciled[1], hydrated), "")
assert.equal(reportCellValue({
	item: "ITEM-1",
	__linked: { item: { item_group: "Hydrated Products" } },
}, reconciled[1]), "Hydrated Products")

const sourceRows = Array.from({ length: 5_001 }, (_value, index) => ({ item: `ITEM-${index}` }))
const batches = buildLinkedValueBatches(sourceRows, [reconciled[1]])
assert.equal(batches.length, 2)
assert.equal(batches[0][0].names.length, 5_000)
assert.equal(batches[1][0].names.length, 1)
assert.deepEqual(batches[0][0].fields, ["item_group"])

const hydratedBatches = await hydrateLinkedValueBatches(
	[[{ source_column: "item", names: ["ITEM-1"] }], [{ source_column: "item", names: ["ITEM-2"] }]],
	async (requests) => ({ item: { [requests[0].names[0]]: { item_group: "Products" } } }),
	() => true,
)
assert.deepEqual(Object.keys(hydratedBatches.item), ["ITEM-1", "ITEM-2"])
let currentHydration = true
const staleHydration = await hydrateLinkedValueBatches(
	[
		[{ source_column: "item", names: ["ITEM-1"] }],
		[{ source_column: "item", names: ["ITEM-2"] }],
	],
	async () => {
		currentHydration = false
		return hydrated
	},
	() => currentHydration,
)
assert.equal(staleHydration, null)

const hydrationLifecycle = createHydrationLifecycle()
const hydrationRequest = hydrationLifecycle.begin()
let hydrationAborted = false
hydrationRequest.signal?.addEventListener("abort", () => { hydrationAborted = true })
let disposedFetches = 0
const disposedHydration = hydrateLinkedValueBatches(
	[
		[{ source_column: "item", names: ["ITEM-1"] }],
		[{ source_column: "item", names: ["ITEM-2"] }],
	],
	async () => {
		disposedFetches += 1
		hydrationLifecycle.invalidate()
		return hydrated
	},
	hydrationRequest.isCurrent,
)
assert.equal(await disposedHydration, null)
assert.equal(disposedFetches, 1)
assert.equal(hydrationAborted, true)
await assert.rejects(
	hydrateLinkedValueBatches([[]], async () => { throw new Error("hydrate failed") }, () => true),
	/hydrate failed/,
)

const savedFetch = globalThis.fetch
const savedWindow = globalThis.window
const requestController = new AbortController()
let forwardedSignal
globalThis.window = { csrf_token: "token", frappe: {} }
globalThis.fetch = async (_url, options) => {
	forwardedSignal = options.signal
	return { status: 200, ok: true, json: async () => ({ message: {} }) }
}
await getLinkedValues("stock-balance", [], { signal: requestController.signal })
assert.equal(forwardedSignal, requestController.signal)
globalThis.fetch = savedFetch
globalThis.window = savedWindow

console.log("report columns OK")
