import assert from "node:assert/strict"
import test from "node:test"
import { createFabricEntries, isMultiColour, useFabricDeliverableContext } from "../src/composables/useFabricDeliverableContext.js"

const context = (qty, extra = {}) => ({
	rows: [{ kind: "identity", qty_rows: [{ key: "Red-32", prefill: qty }], ...extra }],
})
const deferred = () => {
	let resolve, reject
	const promise = new Promise((res, rej) => { resolve = res; reject = rej })
	return { promise, resolve, reject }
}

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
