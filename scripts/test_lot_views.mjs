#!/usr/bin/env node

import assert from "node:assert/strict"
import { readFileSync } from "node:fs"

import {
	LOT_DETAIL_GROUPS,
	lotDetailFields,
	lotDocumentSections,
	lotDocumentContext,
	lotDocumentQuantityLine,
	bomProcessGroups,
	bomUomTotals,
	lotTabCount,
	bomSections,
	formatQuantity,
	formatLotAmount,
	formatLotSummaryValue,
	formatLotTime,
	countLabel,
	isChangedConversion,
	lotTabs,
	orderDetailRows,
	orderItemRows,
	planBadge,
	quantityTotal,
	stepSections,
	visibleConversions,
	weightMatrix,
} from "../frontend/src/departments/purchase/lot/lotViews.js"

assert.deepEqual(lotTabs({}), [{ key: "details", label: "Details" }])
assert.deepEqual(
	lotTabs({
		order_items: null,
		order_details: null,
		bom: null,
		ocr: null,
		fabrics: [],
		other_conversions: [],
	}),
	[{ key: "details", label: "Details" }],
)
assert.deepEqual(
	lotTabs({ order_items: {}, order_details: {}, bom: {}, ocr: {}, fabrics: [{}] }).map(
		(tab) => tab.key,
	),
	["details", "order-items", "order-details", "bom", "ocr", "fabric"],
)
assert.deepEqual(lotTabs({ other_conversions: [{}] }), [
	{ key: "details", label: "Details" },
	{ key: "fabric", label: "Cloth Program" },
])
assert.deepEqual(
	LOT_DETAIL_GROUPS.map((group) => group.key),
	["order", "production", "packing", "bom", "transfer"],
)

const summary = [{ item: "Thread" }]
const additional = [{ item: "Button" }]
assert.deepEqual(bomSections({ summary: [], additional }), [
	{ key: "additional", label: "BOM Additional Items", rows: additional },
])
assert.deepEqual(bomSections({ summary, additional }), [
	{ key: "summary", label: "BOM Summary", rows: summary },
	{ key: "additional", label: "BOM Additional Items", rows: additional },
])
assert.deepEqual(bomSections({}), [])

const items = orderItemRows({
	sizes: ["S", "M"],
	items: [
		{
			attributes: { Colour: "Blue" },
			values: { S: { qty: 2, ratio: 1, mrp: 0 }, M: { qty: 3, ratio: 0, mrp: 0 } },
		},
		{ attributes: { Colour: "Red" }, values: { S: { qty: 1, ratio: 0, mrp: 0 } } },
	],
})
assert.deepEqual(items.columns, ["S", "M"])
assert.deepEqual(items.rows[0], {
	index: 1,
	attributes: { Colour: "Blue" },
	lines: [
		{ key: "qty", label: "Qty", values: { S: 2, M: 3 }, total: 5 },
		{ key: "ratio", label: "Ratio", values: { S: 1, M: 0 }, total: null },
	],
})
assert.deepEqual(
	items.rows[1].lines.map((line) => line.key),
	["qty", "ratio"],
)
assert.deepEqual(
	orderItemRows({ sizes: [], items: [{ attributes: {}, values: { qty: 4, ratio: 0, mrp: 0 } }] }),
	{
		columns: ["Value"],
		rows: [
			{
				index: 1,
				attributes: {},
				lines: [{ key: "qty", label: "Qty", values: { Value: 4 }, total: 4 }],
			},
		],
	},
)
assert.deepEqual(
	orderItemRows({ sizes: [], items: [{ values: { mrp: 100 } }] }).rows[0].lines.map(
		(line) => line.key,
	),
	["qty", "mrp"],
)

const stages = [
	{ key: "quantity", label: "Order" },
	{ key: "cut_qty", label: "Cut" },
]
assert.deepEqual(
	orderDetailRows(
		{
			sizes: ["S", "M"],
			items: [
				{
					attributes: { Colour: "Red" },
					colour_note: "Blue",
					values: { S: { quantity: 2, cut_qty: 1 } },
					totals: { quantity: 2, cut_qty: 1 },
				},
			],
		},
		stages,
	),
	[
		{
			index: 1,
			attributes: { Colour: "Red" },
			colour_note: "Blue",
			lines: [
				{ key: "quantity", label: "Order", values: { S: 2, M: 0 }, total: 2 },
				{ key: "cut_qty", label: "Cut", values: { S: 1, M: 0 }, total: 1 },
			],
		},
	],
)

const matrix = weightMatrix([
	{ dia: "Dia 22", colour: "Red", weight: 2 },
	{ dia: "Dia 8", colour: "Blue", weight: 3 },
	{ dia: "Dia 22", colour: "Red", weight: 4 },
	{ dia: "Dia 8", colour: "Red", weight: 1 },
	{ dia: "Dia 22", colour: "Blue", weight: 0 },
])
assert.deepEqual(matrix.dias, ["Dia 8", "Dia 22"])
assert.deepEqual(matrix.colours, ["Blue", "Red"])
assert.deepEqual(matrix.cells, { "Dia 8": { Blue: 3, Red: 1 }, "Dia 22": { Blue: 0, Red: 6 } })
assert.deepEqual(matrix.diaTotals, { "Dia 8": 4, "Dia 22": 6 })
assert.deepEqual(matrix.colourTotals, { Blue: 3, Red: 7 })
assert.equal(matrix.total, 10)
assert.equal(weightMatrix([{ dia: "20", weight: 2 }]).cells["20"][""], 2)
assert.deepEqual(weightMatrix([]), {
	dias: [],
	colours: [],
	cells: {},
	diaTotals: {},
	colourTotals: {},
	total: 0,
})
assert.equal(
	weightMatrix(
		[{ dia: "18", finished_dia: "22", colour: "Raw", finished_colour: "Blue", weight: 2 }],
		{
			dia: (row) => row.finished_dia || row.dia,
			colour: (row) => row.finished_colour || row.colour,
		},
	).cells["22"].Blue,
	2,
)

assert.deepEqual(
	stepSections([
		{ process_name: "Empty", rows: [] },
		{
			process_name: "Knitting",
			shape: "conversion",
			rows: [
				{ dia: "22", colour: "Blue", planned_weight: 10, received_weight: 12, side: "Output" },
				{ dia: "20", colour: "Raw", planned_weight: 11, received_weight: 9, side: "Input" },
			],
		},
	]),
	[
		{
			process_name: "Knitting",
			shape: "conversion",
			outputs: [{ dia: "22", colour: "Blue", planned: 10, received: 12, balance: -2 }],
			inputs: [{ dia: "20", colour: "Raw", planned: 11, received: 9, balance: 2 }],
		},
	],
)
const conversions = [
	{ planned_item: "A", actual_item: "B" },
	{ planned_item: "A", actual_item: "A" },
]
assert.equal(isChangedConversion(conversions[0]), true)
assert.equal(isChangedConversion(conversions[1]), false)
assert.deepEqual(visibleConversions(conversions), [conversions[0]])
assert.deepEqual(visibleConversions(conversions, true), conversions)
assert.equal(planBadge({}), null)
assert.deepEqual(planBadge({ plan_status: "Built", plan_built_on: "2026-10-14 12:00:00" }), {
	text: "Plan ready 2026-10-14",
	severity: "success",
})
assert.deepEqual(planBadge({ plan_status: "Pending Approval" }), {
	text: "Plan waiting for IPD approval",
	severity: "info",
})
assert.deepEqual(planBadge({ plan_status: "Stale" }), {
	text: "Plan outdated — IPD changed",
	severity: "warn",
})
assert.deepEqual(planBadge({ plan_status: "Error" }), {
	text: "Plan error — open the fabric row",
	severity: "danger",
})
assert.equal(formatQuantity(0), "—")
assert.equal(formatQuantity("2.1259", 3), "2.126")
assert.equal(quantityTotal(0), "0")
assert.equal(quantityTotal(0.0004, 9), "0.0004")

function source(path) {
	return readFileSync(new URL(`../${path}`, import.meta.url), "utf8")
}
const page = source("frontend/src/departments/purchase/lot/LotPage.vue")
const list = source("frontend/src/departments/purchase/lot/LotsList.vue")
const dialog = source("frontend/src/departments/sales/ProductionOrderLotOcrDialog.vue")
const ocr = source("frontend/src/departments/sales/LotOcrTable.vue")
assert.match(page, /DocumentActionStrip/)
assert.doesNotMatch(page, /Time and Action|<Button/)
assert.match(list, /toolbar-actions/)
assert.match(list, /capability\?\.can_create/)
assert.match(list, /allow-bulk-actions="false"/)
assert.match(page, /isCurrentRecordRequest/)
assert.match(page, /id-prefix="lot-details"/)
assert.match(dialog, /import LotOcrTable from "\.\/LotOcrTable\.vue"/)
assert.match(dialog, /<LotOcrTable :payload="payload"/)
assert.doesNotMatch(dialog, /<table>|const processRows|function formatNumber/)
assert.match(ocr, /class="ppo-lot-ocr__table-wrap"/)
for (const doctype of ["YRP Work Order", "SD YRP Cutting Plan", "SD YRP Finishing Plan"])
	assert.ok(ocr.includes(`webDocumentPath('${doctype}', document)`))
assert.match(ocr, /linked: \{ type: Boolean, default: false \}/)

const documents = {
	work_orders: {
		permitted: true,
		count: 12,
		rows: Array.from({ length: 8 }, (_, index) => ({ name: `WO-${index}` })),
	},
	purchase_orders: { permitted: false, count: 0, rows: [] },
}
const sections = lotDocumentSections(documents)
assert.deepEqual(
	sections.map((section) => section.label),
	["Work Orders", "Goods Received Notes", "Delivery Challans"],
)
assert.equal(sections[0].count, 12)
assert.equal(sections[0].visibleRows.length, 5)
assert.equal(lotDocumentSections(documents, {}, 3)[0].visibleRows.length, 3)
assert.equal(lotDocumentSections(documents, { work_orders: true }, 3)[0].visibleRows.length, 8)
assert.equal(lotDocumentSections(documents, {}, 3)[0].hasMore, true)
assert.equal(lotDocumentSections({}, {}, 3)[0].hasMore, false)
assert.equal(
	lotDocumentContext("YRP Work Order", { process_name: "Knitting", supplier_name: "Supplier" }),
	"Knitting · Supplier",
)
assert.equal(
	lotDocumentContext("Purchase Order", { process_name: "Knitting", supplier_name: "Supplier" }),
	"Supplier",
)
assert.equal(
	lotDocumentContext("YRP Goods Received Note", { supplier: "SUP-1", is_return: 1 }),
	"SUP-1 · Return",
)
assert.equal(
	lotDocumentQuantityLine("YRP Work Order", {
		planned_quantity: 100,
		total_no_of_pieces_delivered: 25,
		total_no_of_pieces_received: 10,
	}),
	"Planned 100 · Dlv 25 · Rcv 10",
)
assert.equal(
	lotDocumentQuantityLine("Purchase Order", { lot_qty: 20, grand_total: 1200, currency: "INR" }),
	"Qty 20 · INR 1,200.00",
)
assert.equal(
	lotDocumentQuantityLine("YRP Goods Received Note", { total_received_quantity: 9 }),
	"Rcv 9",
)
assert.equal(lotDocumentQuantityLine("YRP Delivery Challan", { total_delivered_qty: 7 }), "Dlv 7")
assert.deepEqual(
	lotDetailFields({
		header: [
			{ fieldname: "item", value: "hidden" },
			{ fieldname: "uom", value: "Kg" },
		],
		details: [{ fieldname: "total_quantity", value: 12 }],
	}).map((field) => field.fieldname),
	["uom", "total_quantity"],
)
const sparseDetails = [
	{ fieldname: "pack_in_stage", value: "Stitched" },
	{ fieldname: "pack_out_stage", value: "Packed" },
	{ fieldname: "packing_uom", value: "Box" },
	{ fieldname: "total_order_quantity", value: 120 },
	{ fieldname: "total_quantity", value: 100 },
	{ fieldname: "last_calculated_time", value: "2026-10-14 10:00:00" },
]
assert.deepEqual(
	lotDetailFields({ details: sparseDetails, order_details: null, bom: null }),
	sparseDetails,
)
assert.deepEqual(lotTabs({ details: sparseDetails }), [{ key: "details", label: "Details" }])
assert.equal(formatLotAmount(173805.5, "INR"), "INR 1,73,805.50")
assert.equal(formatLotAmount(0, "INR"), "INR 0.00")
assert.equal(formatLotAmount(12.345), "12.35")
assert.equal(formatLotSummaryValue({ fieldtype: "Float", value: 0 }), "—")
assert.equal(formatLotSummaryValue({ fieldtype: "Float", value: 12.5 }), "12.5")
assert.equal(formatLotSummaryValue({ fieldtype: "Currency", value: 0 }, "INR"), "—")
assert.equal(formatLotSummaryValue({ fieldtype: "Currency", value: 34.71 }, "INR"), "INR 34.71")
assert.equal(formatLotTime("9:01:02.658226"), "09:01")
assert.equal(formatLotTime("16:56:54"), "16:56")
assert.equal(formatLotTime(null), "—")
assert.equal(countLabel(1, "row"), "1 row")
assert.equal(countLabel(2, "row"), "2 rows")
assert.equal(countLabel(1, "process", "processes"), "1 process")
assert.equal(countLabel(2, "process", "processes"), "2 processes")
assert.ok(LOT_DETAIL_GROUPS.every((group) => group.description))
assert.equal(lotTabCount({}, "details"), null)
assert.equal(lotTabCount({}, "ocr"), null)
assert.equal(
	lotTabCount({ order_details: { groups: [{ items: [1, 2] }, { items: [3] }] } }, "order-details"),
	3,
)
assert.deepEqual(
	bomProcessGroups([
		{ process_name: "Z", item: "B" },
		{ process_name: "A", item: "C" },
		{ process_name: "A", item: "A" },
	]).map((group) => [group.process, group.rows.map((row) => row.item)]),
	[
		["A", ["A", "C"]],
		["Z", ["B"]],
	],
)
assert.deepEqual(
	bomUomTotals([
		{ uom: "Kg", required_qty: 2 },
		{ uom: "Kg", required_qty: 3 },
		{ uom: "Nos", required_qty: 4 },
	]),
	[
		{ uom: "Kg", total: 5 },
		{ uom: "Nos", total: 4 },
	],
)


const { conversionProcesses, conversionView } = await import('../frontend/src/departments/purchase/lot/lotViews.js')
const conversionRows = [
	{ process_name: 'Washing', process_stage_index: 2, planned_item: 'Blue-14', actual_item: 'Blue-14.5', production_detail: 'IPD-CLOTH' },
	{ process_name: 'Knitting', process_stage_index: 0, planned_item: 'Greige-14', actual_item: 'Greige-14.5', production_detail: 'IPD-CLOTH' },
	{ process_name: 'Dyeing', process_stage_index: 1, planned_item: 'Blue-14', actual_item: 'Blue-14.5', production_detail: 'IPD-CLOTH' },
	{ process_name: 'Knitting', process_stage_index: 0, planned_item: 'Greige-19', actual_item: 'Greige-19', production_detail: 'IPD-OTHER' },
]
assert.deepEqual(conversionProcesses(conversionRows), ['Knitting', 'Dyeing', 'Washing'])
assert.deepEqual(conversionProcesses([{ process_name: 'Washing' }, { process_name: 'Dyeing' }, { process_name: 'Knitting' }]), ['Knitting', 'Dyeing', 'Washing'])
assert.deepEqual(conversionView(conversionRows), { rows: conversionRows.slice(0, 3), changed: 3, routes: 4 })
assert.equal(conversionView(conversionRows, { includeUnchanged: true }).rows.length, 4)
assert.equal(conversionView(conversionRows, { search: ' 14.5 ' }).rows.length, 3)
assert.equal(conversionView(conversionRows, { process: 'Dyeing' }).changed, 3)
assert.equal(conversionView(conversionRows, { search: 'IPD-OTHER', includeUnchanged: true }).rows.length, 1)
assert.equal(conversionView(conversionRows, { search: 'knitting', includeUnchanged: true }).routes, 4)
assert.equal(conversionView(conversionRows, { search: 'missing' }).routes, 4)
const lotConversions = [
	...conversionRows.slice(0, 3),
	...['19', '20'].flatMap((dia) => ['Knitting', 'Dyeing', 'Washing'].map((process_name) => ({ process_name, planned_item: `Greige-${dia}`, actual_item: `Greige-${dia}` }))),
]
for (const options of [
	{}, { search: '14.5' }, { process: 'Dyeing' }, { includeUnchanged: true },
	{ search: '19', process: 'Knitting', includeUnchanged: true }, { search: 'missing' },
]) {
	const view = conversionView(lotConversions, options)
	assert.equal(view.changed, 3, 'header keeps Lot changed total')
	assert.equal(view.routes, 9, 'header keeps Lot route total')
}
assert.equal(conversionView(lotConversions, { search: '14.5' }).rows.length, 3)
assert.equal(conversionView(lotConversions, { process: 'Dyeing' }).rows.length, 1)
assert.equal(conversionView(lotConversions, { includeUnchanged: true }).rows.length, 9)
assert.equal(conversionView(lotConversions, { search: 'missing' }).rows.length, 0)
assert.deepEqual(conversionView(), { rows: [], changed: 0, routes: 0 })

console.log("lot views OK")
