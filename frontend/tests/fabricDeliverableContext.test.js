import assert from "node:assert/strict"
import test from "node:test"
import {
	collectManualKnittingContract,
	createFabricEntries,
	isMultiColour,
	knittingInputRouteKey,
	useFabricDeliverableContext,
} from "../src/composables/useFabricDeliverableContext.js"
import * as fabricContext from "../src/composables/useFabricDeliverableContext.js"

const context = (qty, extra = {}) => ({
	rows: [{ kind: "identity", qty_rows: [{ key: "Red-32", prefill: qty }], ...extra }],
})
const deferred = () => {
	let resolve, reject
	const promise = new Promise((res, rej) => { resolve = res; reject = rej })
	return { promise, resolve, reject }
}

test("colour-dia layout keeps one prominent Dia group for duplicate stock rows", () => {
	assert.equal(typeof fabricContext.buildColourDiaLayout, "function")
	const layout = fabricContext.buildColourDiaLayout({
		kind: "dyeing",
		reference_routed: true,
		qty_rows: [
			{ key: "grey-26-a", section: "Grey", row_label: "26 Dia" },
			{ key: "grey-26-b", section: "Grey", row_label: "26 Dia" },
			{ key: "grey-36", section: "Grey", row_label: "36 Dia" },
			{ key: "navy-26", section: "Navy", row_label: "26 Dia" },
		],
	})

	assert.deepEqual(
		layout.sections.map((section) => ({
			colour: section.name,
			dias: section.diaGroups.map((group) => [group.name, group.items.map((item) => item.j)]),
		})),
		[
			{ colour: "Grey", dias: [["26 Dia", [0, 1]], ["36 Dia", [2]]] },
			{ colour: "Navy", dias: [["26 Dia", [3]]] },
		],
	)
})

test("keeps saved program quantities for each finished colour and dia, not greige columns", () => {
	const row = {
		kind: "knitting", reference_routed: true, has_colour: true, ratio: 3,
		greige_colour: "Greige", colour_options: ["Greige", "Navy", "Green"],
		qty_rows: [
			{ section: "Red", row_label: "18 Dia", prefill: 100, knit_colour: "Greige" },
			{ section: "Red", row_label: "22 Dia", prefill: 50, knit_colour: "Greige" },
			{ section: "Navy", row_label: "18 Dia", prefill: 80, knit_colour: "Navy" },
			{ section: "Green", row_label: "22 Dia", prefill: 70, knit_colour: "Green" },
		],
	}
	assert.equal(isMultiColour(row), false)
	const [entry] = createFabricEntries({ rows: [row] })
	assert.deepEqual(entry.qtys, [100, 50, 80, 70])
	assert.deepEqual(entry.colourQtys, {})
	assert.equal(entry.yarnQty, 100)
})

test("shared GRN pools stay explicitly zero for manual allocation", () => {
	const [entry] = createFabricEntries(context(0, {
		qty_rows: [
			{ prefill: 0, source_available: 150, source_shared: true },
			{ prefill: 0, source_available: 150, source_shared: true },
			{ prefill: 60, source_available: 60, source_shared: false },
		],
	}))
	assert.deepEqual(entry.qtys, [0, 0, 60])
})

test("missing defaults stay blank, with zero preserved", () => {
	const [entry] = createFabricEntries(context(0, { qty_rows: [{}, { prefill: null }, { prefill: 0 }] }))
	assert.deepEqual(entry.qtys, [null, null, 0])
})

test("legacy knitting only prefills its configured default colour and computes yarn", () => {
	const [entry] = createFabricEntries(context(30, {
		kind: "knitting", has_colour: true, colour_options: ["Greige", "Navy"], greige_colour: "Greige", ratio: 3,
	}))
	assert.deepEqual(entry.colourQtys, { Greige: [30], Navy: [null] })
	assert.equal(entry.colour, null)
	assert.equal(entry.yarnQty, 10)
})

test("manual knitting prefills each route's editable yarn contract", () => {
	const [entry] = createFabricEntries({
		rows: [{
			kind: "knitting",
			manual_io: true,
			reference_routed: true,
			qty_rows: [{
			prefill: 100,
			knitting_inputs: [
				{ key: "input:0", qty_per_output: 0.6, prefill: 59 },
				{ key: "input:1", qty_per_output: 0.4, prefill: 41 },
			],
			}],
		}],
	})
	assert.deepEqual(
		entry.knittingInputQtys[knittingInputRouteKey(0)],
		[59, 41],
	)
	entry.knittingInputQtys[knittingInputRouteKey(0)][0] = 61
	assert.equal(entry.qtys[0], 100)
})

test("manual knitting shows each physical deliverable and receivable only once", () => {
	const row = {
		kind: "knitting",
		manual_io: true,
		reference_routed: true,
		has_colour: true,
		cloth_item: "Finished Cloth",
		qty_rows: [
			{
				key: "route:red",
				prefill: 60,
				out_attrs: { Dia: "36 Dia", Colour: "Red" },
				knit_colour: "Greige",
				knitting_inputs: [
					{ key: "input:0", item: "Yarn A", attrs: { Colour: "Greige" }, uom: "Kg", qty_per_output: 0.59, prefill: 35.4 },
					{ key: "input:1", item: "Yarn B", attrs: { Colour: "Greige" }, uom: "Kg", qty_per_output: 0.41, prefill: 24.6 },
				],
			},
			{
				key: "route:maroon",
				prefill: 40,
				out_attrs: { Dia: "36 Dia", Colour: "Maroon" },
				knit_colour: "Greige",
				knitting_inputs: [
					{ key: "input:0", item: "Yarn A", attrs: { Colour: "Greige" }, uom: "Kg", qty_per_output: 0.59, prefill: 23.6 },
					{ key: "input:1", item: "Yarn B", attrs: { Colour: "Greige" }, uom: "Kg", qty_per_output: 0.41, prefill: 16.4 },
				],
			},
		],
	}
	const [entry] = createFabricEntries({ rows: [row] })

	assert.equal(entry.manualReceivables.length, 1)
	assert.equal(entry.manualReceivables[0].qty, 100)
	assert.deepEqual(entry.manualReceivables[0].attrs, { Dia: "36 Dia", Colour: "Greige" })
	assert.deepEqual(
		entry.manualDeliverables.map((item) => [item.item, item.qty]),
		[["Yarn A", 59], ["Yarn B", 41]],
	)

	entry.manualReceivables[0].qty = 80
	entry.manualDeliverables[0].qty = 48
	entry.manualDeliverables[1].qty = 32
	const contract = collectManualKnittingContract(row, entry)
	assert.deepEqual(contract.routes.map((route) => route.qty), [48, 32])
	assert.deepEqual(
		contract.routes.map((route) => route.manualInputs.map((input) => input.qty)),
		[[28.8, 19.2], [19.2, 12.8]],
	)
	assert.deepEqual(contract.orphanDeliverables, [])
})

test("manual knitting rejects yarn totals with no physical fabric receivable", () => {
	const row = {
		kind: "knitting",
		manual_io: true,
		cloth_item: "Cloth",
		qty_rows: [{
			key: "route:1",
			prefill: 0,
			out_attrs: { Dia: "36 Dia" },
			knitting_inputs: [{
				key: "input:0", item: "Yarn", attrs: {}, uom: "Kg", qty_per_output: 1,
			}],
		}],
	}
	const [entry] = createFabricEntries({ rows: [row] })
	entry.manualDeliverables[0].qty = 10
	const contract = collectManualKnittingContract(row, entry)
	assert.equal(contract.orphanDeliverables.length, 1)
	assert.equal(contract.routes[0].qty, 0)
})

test("manual knitting keeps distinct IPD alternatives even when their planned quantity is zero", () => {
	const [entry] = createFabricEntries({
		rows: [{
			kind: "knitting",
			manual_io: true,
			reference_routed: true,
			has_colour: true,
			cloth_item: "Cloth",
			qty_rows: [
				{
					key: "planned",
					prefill: 25,
					out_attrs: { Dia: "34 Dia", Colour: "Greige" },
					knit_colour: "Greige",
					knitting_inputs: [{ key: "input:0", item: "Yarn", attrs: { Colour: "Greige" }, uom: "Kg", qty_per_output: 1 }],
				},
				{
					key: "unused",
					prefill: 0,
					out_attrs: { Dia: "36 Dia", Colour: "Red" },
					knit_colour: "Red",
					knitting_inputs: [{ key: "input:0", item: "Yarn", attrs: { Colour: "Red" }, uom: "Kg", qty_per_output: 1 }],
				},
			],
		}],
	})
	assert.deepEqual(entry.manualReceivables.map((item) => [item.attrs, item.qty]), [
		[{ Dia: "34 Dia", Colour: "Greige" }, 25],
		[{ Dia: "36 Dia", Colour: "Red" }, 0],
	])
	assert.deepEqual(entry.manualDeliverables.map((item) => [item.attrs, item.qty]), [
		[{ Colour: "Greige" }, 25],
		[{ Colour: "Red" }, 0],
	])
})

test("many-colour legacy knitting keeps the single-colour fallback", () => {
	const row = { kind: "knitting", has_colour: true, colour_options: Array.from({ length: 7 }, (_, i) => `Colour ${i}`) }
	assert.equal(isMultiColour(row), false)
})

test("editing a prefilled quantity never mutates the server context", () => {
	const source = context(90)
	const [entry] = createFabricEntries(source)
	entry.qtys[0] = 75
	assert.equal(source.rows[0].qty_rows[0].prefill, 90)
})

test("loads plan defaults, then passes the exact selected process step to the same endpoint", async () => {
	const calls = []
	const state = useFabricDeliverableContext(async (args) => {
		calls.push(args)
		return { ...context(args.source_process ? 90 : 100), source_process: args.source_process ? { value: args.source_process } : null }
	})
	assert.equal(await state.load("WO-1", null, { reset: true }), true)
	assert.deepEqual(state.entries.value[0].qtys, [100])
	assert.equal(await state.load("WO-1", "2::Dyeing"), true)
	assert.deepEqual(state.entries.value[0].qtys, [90])
	assert.equal(state.ctx.value.source_process.value, "2::Dyeing")
	assert.deepEqual(calls, [
		{ work_order: "WO-1", source_process: null },
		{ work_order: "WO-1", source_process: "2::Dyeing" },
	])
})

test("an incompatible or empty GRN source preserves edited values and prior source", async () => {
	const state = useFabricDeliverableContext(async ({ source_process }) => {
		if (source_process === "0::Knitting") throw new Error("no compatible input row")
		return { ...context(90), source_process: { value: "2::Dyeing" } }
	})
	await state.load("WO-1", "2::Dyeing")
	state.entries.value[0].qtys[0] = 75
	await assert.rejects(state.load("WO-1", "0::Knitting"), /no compatible/)
	assert.deepEqual(state.entries.value[0].qtys, [75])
	assert.equal(state.ctx.value.source_process.value, "2::Dyeing")
	assert.equal(state.loading.value, false)
})

test("a response after closing cannot repopulate or replace the popup", async () => {
	const pending = deferred()
	const state = useFabricDeliverableContext(() => pending.promise)
	const request = state.load("WO-1")
	state.invalidate()
	pending.resolve(context(90))
	assert.equal(await request, false)
	assert.equal(state.ctx.value, null)
	assert.equal(state.loading.value, false)
})

test("only the latest Work Order request can update quantities", async () => {
	const pending = [deferred(), deferred()]
	let index = 0
	const state = useFabricDeliverableContext(() => pending[index++].promise)
	const oldRequest = state.load("WO-1")
	const currentRequest = state.load("WO-2", null, { reset: true })
	pending[1].resolve(context(50))
	await currentRequest
	pending[0].resolve(context(99))
	assert.equal(await oldRequest, false)
	assert.deepEqual(state.entries.value[0].qtys, [50])
})

test("a stale failure cannot cancel the current loading state", async () => {
	const pending = [deferred(), deferred()]
	let index = 0
	const state = useFabricDeliverableContext(() => pending[index++].promise)
	const oldRequest = state.load("WO-1")
	const currentRequest = state.load("WO-2")
	pending[0].reject(new Error("old request failed"))
	assert.equal(await oldRequest, false)
	assert.equal(state.loading.value, true)
	pending[1].resolve(context(50))
	await currentRequest
	assert.equal(state.loading.value, false)
})

test("reopening resets the selected source and edits to fresh saved plan quantities", async () => {
	const state = useFabricDeliverableContext(async ({ source_process }) => ({
		...context(source_process ? 90 : 100), source_process: source_process ? { value: source_process } : null,
	}))
	await state.load("WO-1", "2::Dyeing")
	state.entries.value[0].qtys[0] = 70
	state.invalidate()
	await state.load("WO-1", null, { reset: true })
	assert.equal(state.ctx.value.source_process, null)
	assert.deepEqual(state.entries.value[0].qtys, [100])
})
