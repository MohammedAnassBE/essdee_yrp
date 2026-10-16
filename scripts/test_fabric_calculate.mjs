import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { computed, reactive, ref, watch } from '../frontend/node_modules/vue/index.mjs'
import * as fabricCalculate from '../frontend/src/departments/fabric-store/fabricCalculate.js'
import { findNodes, loadComponent, mountComponent, Vue } from './helpers/vue_renderer.mjs'

const {
	buildFabricPayload, canCalculateFabric, fabricColourError, fabricEntryError, fabricEntryLabel,
	fabricPlanningHint, fabricSourceProcess, fabricUnavailableMessage, fabricWarnings, fabricYarnTotals,
	hydrateFabricRows, setFabricClothQuantity,
} = fabricCalculate

const cloth = 'Cotton Poly 58/42 Jersey Fabric'
const knittingMatrix = `${cloth}-2-Knitting-`
const dyeingMatrix = `${cloth}-2-Dyeing-`
const yarnOptions = [
	{ key: 'input:0', item: "Yarn 40's VL", attrs: { Colour: 'Greige' }, uom: 'Kg', qty_per_output: 0.58 },
	{ key: 'input:1', item: 'Yarn 100D Poly Yarn', attrs: { Colour: 'Greige' }, uom: 'Kg', qty_per_output: 0.42 },
]

function knittingRoute(matrix, dia, prefill, yarnPrefills) {
	return {
		key: `${knittingMatrix}${matrix}:0`, label: `White · ${dia} Dia`, section: 'White', row_label: `${dia} Dia`,
		out_attrs: { Dia: `${dia} Dia`, Colour: 'Greige' }, target_attrs: { Colour: 'White', Dia: `${dia} Dia` },
		reference_item_variant: `White-${dia}`, knit_colour: 'Greige', program: 328, ordered: 0, balance: 328, prefill,
		knitting_inputs: yarnOptions.map((input, index) => ({ ...input, ...(yarnPrefills ? { prefill: yarnPrefills[index] } : {}) })),
	}
}

const knittingContext = {
	is_fabric_process: true, kind: 'knitting', warnings: [], source_process: null, source_process_options: [],
	rows: [{
		fabric_row: 'jop24hqf8v', cloth_item: cloth, production_detail: `${cloth}-2`, kind: 'knitting',
		manual_io: true, reference_routed: true, has_colour: true, greige_colour: 'Greige', colour_options: ['Greige'],
		yarns: [], ratio: 1, qty_rows: [knittingRoute('316998', 19, 30, [18.32, 13.26]), knittingRoute('316993', 14, 50, [30.53, 22.1])],
	}],
}

function sourceRoute(key, matrix, dia, amount, bucket) {
	return {
		key: `fabric-${key}`, matrix_key: `${dyeingMatrix}${matrix}:0`, out_attrs: { Colour: 'White', Dia: `${dia} Dia` },
		label: `Greige → White · ${dia === 14.5 ? '14.5 Dia (actual, for 14 Dia)' : `${dia} Dia`}`,
		section: 'White', row_label: `${dia} Dia`, prefill: amount, knitting_inputs: [],
		source_bucket_key: `fabric-source-${bucket}`, source_mode: 'exact', source_process: 'Knitting',
		source_pool_key: `fabric-source-${bucket}`, source_grn: 'GRN-00008', source_grn_row: 1,
		source_stock_available: amount, source_stock_per_output: 1, source_available: amount,
	}
}

const dyeingContext = {
	is_fabric_process: true, kind: 'dyeing', warnings: [],
	source_process: { value: '0::Knitting', label: 'Knitting', process_name: 'Knitting', unavailable: false },
	source_process_options: [{ value: '0::Knitting', label: 'Knitting' }],
	rows: [{
		fabric_row: 'jop24hqf8v', cloth_item: cloth, production_detail: `${cloth}-2`, kind: 'dyeing',
		manual_io: false, reference_routed: false, has_colour: true, yarns: [], qty_rows: [
			sourceRoute('552432da0bfe6de51e388f5a', '317004', 19, 34, '44f8fe1f2deccb23176e1a26'),
			sourceRoute('9b61c5670944c2d6d4ac30bd', '316999', 14, 35, '0c2c73e2454beb4b5af304ae'),
			sourceRoute('27324ec14d825399f51a5004', '316999', 14.5, 20, '83d2550bd321f77d486fd440'),
		],
	}],
}

function decodeDeskBody(body) {
	const parameters = new URLSearchParams(body)
	return { work_order: parameters.get('work_order'), rows: JSON.parse(parameters.get('rows')), source_process: parameters.get('source_process') || null }
}

const deskKnitting = decodeDeskBody('work_order=YRP-WO-2026-00008&rows=%5B%7B%22fabric_row%22%3A%22jop24hqf8v%22%2C%22colour%22%3Anull%2C%22yarn_qty%22%3Anull%2C%22entries%22%3A%5B%7B%22key%22%3A%22Cotton+Poly+58%2F42+Jersey+Fabric-2-Knitting-316998%3A0%22%2C%22matrix_key%22%3A%22Cotton+Poly+58%2F42+Jersey+Fabric-2-Knitting-316998%3A0%22%2C%22out_attrs%22%3A%7B%22Dia%22%3A%2219+Dia%22%2C%22Colour%22%3A%22Greige%22%7D%2C%22qty%22%3A30%2C%22colour%22%3A%22Greige%22%2C%22inputs%22%3A%5B%7B%22key%22%3A%22input%3A0%22%2C%22qty%22%3A18.32%7D%2C%7B%22key%22%3A%22input%3A1%22%2C%22qty%22%3A13.26%7D%5D%7D%2C%7B%22key%22%3A%22Cotton+Poly+58%2F42+Jersey+Fabric-2-Knitting-316993%3A0%22%2C%22matrix_key%22%3A%22Cotton+Poly+58%2F42+Jersey+Fabric-2-Knitting-316993%3A0%22%2C%22out_attrs%22%3A%7B%22Dia%22%3A%2214+Dia%22%2C%22Colour%22%3A%22Greige%22%7D%2C%22qty%22%3A50%2C%22colour%22%3A%22Greige%22%2C%22inputs%22%3A%5B%7B%22key%22%3A%22input%3A0%22%2C%22qty%22%3A30.53%7D%2C%7B%22key%22%3A%22input%3A1%22%2C%22qty%22%3A22.1%7D%5D%7D%5D%7D%5D&source_process=')
const deskDyeing = decodeDeskBody('work_order=YRP-WO-2026-00009&rows=%5B%7B%22fabric_row%22%3A%22jop24hqf8v%22%2C%22colour%22%3Anull%2C%22yarn_qty%22%3Anull%2C%22entries%22%3A%5B%7B%22key%22%3A%22fabric-552432da0bfe6de51e388f5a%22%2C%22matrix_key%22%3A%22Cotton+Poly+58%2F42+Jersey+Fabric-2-Dyeing-317004%3A0%22%2C%22out_attrs%22%3A%7B%22Dia%22%3A%2219+Dia%22%2C%22Colour%22%3A%22White%22%7D%2C%22qty%22%3A34%2C%22source_bucket_key%22%3A%22fabric-source-44f8fe1f2deccb23176e1a26%22%2C%22source_mode%22%3A%22exact%22%7D%2C%7B%22key%22%3A%22fabric-9b61c5670944c2d6d4ac30bd%22%2C%22matrix_key%22%3A%22Cotton+Poly+58%2F42+Jersey+Fabric-2-Dyeing-316999%3A0%22%2C%22out_attrs%22%3A%7B%22Colour%22%3A%22White%22%2C%22Dia%22%3A%2214+Dia%22%7D%2C%22qty%22%3A35%2C%22source_bucket_key%22%3A%22fabric-source-0c2c73e2454beb4b5af304ae%22%2C%22source_mode%22%3A%22exact%22%7D%2C%7B%22key%22%3A%22fabric-27324ec14d825399f51a5004%22%2C%22matrix_key%22%3A%22Cotton+Poly+58%2F42+Jersey+Fabric-2-Dyeing-316999%3A0%22%2C%22out_attrs%22%3A%7B%22Colour%22%3A%22White%22%2C%22Dia%22%3A%2214.5+Dia%22%7D%2C%22qty%22%3A20%2C%22source_bucket_key%22%3A%22fabric-source-83d2550bd321f77d486fd440%22%2C%22source_mode%22%3A%22exact%22%7D%5D%7D%5D&source_process=0%3A%3AKnitting')

const knittingRows = hydrateFabricRows(knittingContext)
const dyeingRows = hydrateFabricRows(dyeingContext)
assert.deepEqual({ work_order: deskKnitting.work_order, ...buildFabricPayload(knittingContext, knittingRows) }, deskKnitting)
assert.deepEqual({ work_order: deskDyeing.work_order, ...buildFabricPayload(dyeingContext, dyeingRows) }, deskDyeing)
assert.equal(knittingRows[0].entries[0].matrix_key, undefined, 'plain rows exercise matrix key fallback')
assert.equal(Object.hasOwn(buildFabricPayload(dyeingContext, dyeingRows).rows[0].entries[0], 'colour'), false)
assert.equal(Object.hasOwn(buildFabricPayload(dyeingContext, dyeingRows).rows[0].entries[0], 'inputs'), false)
console.log('C4/C8: captured Knitting and Dyeing Desk bodies match exactly')

const washingContext = structuredClone(dyeingContext)
washingContext.kind = washingContext.rows[0].kind = 'identity'
washingContext.source_process = { value: '1::Dyeing', label: 'Dyeing' }
washingContext.source_process_options = [{ value: '1::Dyeing', label: 'Dyeing' }]
washingContext.rows[0].qty_rows = [{
	key: 'fabric-washing', matrix_key: `${cloth}-2-Washing-1:0`, out_attrs: { Colour: 'White', Dia: '14.5 Dia' },
	label: 'White · 14.5 Dia', prefill: 20, source_bucket_key: 'fabric-source-dyeing', source_mode: 'exact',
	source_process: 'Dyeing', source_grn: 'GRN-00009', source_available: 20,
}]
const washingRows = hydrateFabricRows(washingContext)
assert.deepEqual(buildFabricPayload(washingContext, washingRows), {
	source_process: '1::Dyeing', rows: [{ fabric_row: 'jop24hqf8v', colour: null, yarn_qty: null, entries: [{
		key: 'fabric-washing', matrix_key: `${cloth}-2-Washing-1:0`, out_attrs: { Colour: 'White', Dia: '14.5 Dia' },
		qty: 20, source_bucket_key: 'fabric-source-dyeing', source_mode: 'exact',
	}] }],
})
assert.equal(fabricSourceProcess(dyeingContext), '0::Knitting')
assert.equal(fabricSourceProcess({ source_process_options: [{ value: '1::Dyeing' }] }), '1::Dyeing')
assert.equal(buildFabricPayload(washingContext, washingRows).source_process, '1::Dyeing', 'payload uses the loaded source')
assert.equal(buildFabricPayload({ source_process_options: [{ value: '1::Dyeing' }] }, []).source_process, '1::Dyeing')
assert.equal(fabricSourceProcess({}), null)
console.log('C5/C8/C14: source defaults, selection and Washing exact-source body OK')

const knittingRow = knittingRows[0]
const route = knittingRow.entries[0]
assert.equal(fabricPlanningHint(knittingRow, route), 'Program 328 · Ordered 0 · Balance 328')
assert.equal(fabricYarnTotals(knittingRow).total, 84.21)
assert.deepEqual(fabricYarnTotals(knittingRow).items.map((input) => input.qty), [48.85, 35.36])
setFabricClothQuantity(knittingRow, route, 30)
assert.deepEqual(route.inputs.map((input) => input.qty), [18.32, 13.26], 'unchanged cloth keeps saved yarn')
route.inputs[0].qty = 25
setFabricClothQuantity(knittingRow, route, '30')
assert.equal(route.inputs[0].qty, 25, 'manual yarn survives repeated cloth events')
setFabricClothQuantity(knittingRow, route, 40)
assert.deepEqual(route.inputs.map((input) => input.qty), [23.2, 16.8])
setFabricClothQuantity(knittingRow, route, 30)
assert.deepEqual(route.inputs.map((input) => input.qty), [17.4, 12.6])
assert.deepEqual(knittingRow.entries[1].inputs.map((input) => input.qty), [30.53, 22.1], 'other routes stay untouched')
setFabricClothQuantity(knittingRow, route, 30.123)
assert.deepEqual(route.inputs.map((input) => input.qty), [17.47, 12.65], 're-split rounds to two decimals')
const initialContext = structuredClone(knittingContext)
initialContext.rows[0].qty_rows = [knittingRoute('1', 19, 328)]
const initial = hydrateFabricRows(initialContext)[0]
assert.equal(initial.entries[0].qty, 328)
assert.deepEqual(initial.entries[0].inputs.map((input) => input.qty), [190.24, 137.76])
initialContext.rows[0].qty_rows[0].knitting_inputs[0].prefill = 0
assert.equal(hydrateFabricRows(initialContext)[0].entries[0].inputs[0].qty, 0, 'explicit saved zero is retained')
initialContext.rows[0].qty_rows[0].knitting_inputs[0].prefill = 190.245
assert.equal(hydrateFabricRows(initialContext)[0].entries[0].inputs[0].qty, 190.24, 'saved yarn uses Desk half-even rounding')
assert.equal(knittingContext.rows[0].qty_rows[0].knitting_inputs[0].prefill, 18.32, 'hydration does not mutate context')
console.log('C6/C9/C10/C12: saved prefills, per-route re-split and live totals OK')

const multiColourContext = structuredClone(knittingContext)
multiColourContext.rows[0].reference_routed = false
multiColourContext.rows[0].colour_options = ['Greige', 'Melange']
multiColourContext.rows[0].qty_rows = [knittingRoute('1', 19, 30, [30, 30])]
const multiColourRows = hydrateFabricRows(multiColourContext)
assert.equal(multiColourRows[0].multi_colour, true)
assert.deepEqual(multiColourRows[0].entries.map((entry) => ({
	colour: entry.colour, cloth: entry.qty, yarn: entry.inputs.map((input) => input.qty),
})), [
	{ colour: 'Greige', cloth: 30, yarn: [30, 30] },
	{ colour: 'Melange', cloth: 0, yarn: [0, 0] },
])
assert.equal(canCalculateFabric(multiColourContext, multiColourRows), true)
assert.equal(multiColourContext.rows[0].qty_rows[0].knitting_inputs[0].prefill, 30)
console.log('Multi-colour: only the default colour keeps yarn prefills; Calculate is enabled')

const precisionContext = structuredClone(knittingContext)
precisionContext.rows[0].qty_rows = [knittingRoute('1', 18, 1101.105, [349.831, 253.326])]
const precisionRows = hydrateFabricRows(precisionContext)
const precisionEntry = precisionRows[0].entries[0]
assert.equal(precisionEntry.qty, 1101.1)
assert.deepEqual(precisionEntry.inputs.map((input) => input.qty), [349.83, 253.33])
const prefilledPayload = buildFabricPayload(precisionContext, precisionRows).rows[0].entries[0]
assert.equal(prefilledPayload.qty, 1101.1)
assert.deepEqual(prefilledPayload.inputs.map((input) => input.qty), [349.83, 253.33])
console.log('Precision: accepted cloth and yarn prefills round to Desk Float precision')

setFabricClothQuantity(precisionRows[0], precisionEntry, 30.123)
precisionEntry.inputs[0].qty = 349.831
precisionEntry.inputs[1].qty = 253.326
const typedPayload = buildFabricPayload(precisionContext, precisionRows).rows[0].entries[0]
assert.equal(typedPayload.qty, 30.12)
assert.deepEqual(typedPayload.inputs.map((input) => input.qty), [349.83, 253.33])
console.log('Precision: typed cloth and yarn quantities round to Desk Float precision')

precisionContext.rows[0].qty_rows = [knittingRoute('1', 18, 1101.105)]
const fallbackEntry = hydrateFabricRows(precisionContext)[0].entries[0]
assert.equal(fallbackEntry.qty, 1101.1)
assert.deepEqual(fallbackEntry.inputs.map((input) => input.qty), [638.64, 462.46])
console.log('Precision: fallback yarn quantities use rounded cloth and Desk Float precision')

const roundingCases = [
	[191.705, 191.7, [111.19, 80.51]], [40.905, 40.9, [23.72, 17.18]],
	[1101.105, 1101.1, [638.64, 462.46]], [0.125, 0.12, [0.07, 0.05]], [0.135, 0.14, [0.08, 0.06]],
]
for (const [value, expected, expectedInputs] of roundingCases) {
	const context = structuredClone(knittingContext)
	context.rows[0].qty_rows = [knittingRoute('1', 19, value, [value, value])]
	const rows = hydrateFabricRows(context)
	const entry = rows[0].entries[0]
	assert.equal(entry.qty, expected, `cloth prefill ${value} rounds half to even`)
	assert.deepEqual(entry.inputs.map((input) => input.qty), [expected, expected], `yarn prefill ${value} rounds half to even`)
	setFabricClothQuantity(rows[0], entry, 1)
	setFabricClothQuantity(rows[0], entry, value)
	assert.equal(entry.qty, expected, `typed cloth ${value} rounds half to even before re-split`)
	assert.deepEqual(entry.inputs.map((input) => input.qty), expectedInputs, 're-split uses the rounded cloth quantity')
	entry.qty = value
	for (const input of entry.inputs) input.qty = value
	const payload = buildFabricPayload(context, rows).rows[0].entries[0]
	assert.equal(payload.qty, expected, `cloth payload ${value} rounds half to even`)
	assert.deepEqual(payload.inputs.map((input) => input.qty), [expected, expected], `yarn payload ${value} rounds half to even`)
	context.rows[0].qty_rows[0].prefill = 1
	context.rows[0].qty_rows[0].knitting_inputs = [{ ...yarnOptions[0], qty_per_output: value }]
	assert.equal(hydrateFabricRows(context)[0].entries[0].inputs[0].qty, expected, `fallback yarn ${value} rounds half to even`)
}
console.log('Precision: 191.705, 40.905, 1101.105, 0.125 and 0.135 use Desk half-even rounding')

const resplitContext = structuredClone(knittingContext)
resplitContext.rows[0].qty_rows = [knittingRoute('1', 19, 2)]
resplitContext.rows[0].qty_rows[0].knitting_inputs[0].qty_per_output = 18.3149
const resplitRows = hydrateFabricRows(resplitContext)
const resplitEntry = resplitRows[0].entries[0]
setFabricClothQuantity(resplitRows[0], resplitEntry, 1)
assert.equal(resplitEntry.inputs[0].qty, 18.32, '18.3149 first rounds to 18.315, then half-even to 18.32')
assert.equal(buildFabricPayload(resplitContext, resplitRows).rows[0].entries[0].inputs[0].qty, 18.32)
console.log('Precision: re-split rounds to three decimals before Desk half-even rounding to two')

setFabricClothQuantity(knittingRow, route, 0)
route.inputs[0].qty = 1
assert.match(fabricEntryError(knittingRow, route), /expected cloth quantity/)
assert.equal(canCalculateFabric(knittingContext, knittingRows), false, 'orphan yarn blocks even with another valid route')
route.inputs[0].qty = 0
assert.equal(fabricEntryError(knittingRow, route), '')
setFabricClothQuantity(knittingRow, route, 1)
for (const input of route.inputs) input.qty = 0
assert.match(fabricEntryError(knittingRow, route), /at least one yarn/)
assert.equal(canCalculateFabric(knittingContext, knittingRows), false)
setFabricClothQuantity(knittingRow, route, 400)
assert.equal(canCalculateFabric(knittingContext, knittingRows), true)
assert.equal(fabricWarnings(knittingRows)[0], `${cloth} · ${route.label}: 400 > balance 328`, 'warning names the cloth once')
assert.equal(fabricColourError(knittingRow), '')
assert.match(fabricEntryLabel(dyeingRows[0].entries[2]), /14.5 Dia \(actual, for 14 Dia\)/)
assert.equal(fabricPlanningHint(dyeingRows[0], dyeingRows[0].entries[2]), 'GRN-00008 · row 1 · 20 Kg available')
assert.equal(buildFabricPayload(dyeingContext, dyeingRows).rows[0].entries[2].out_attrs.Dia, '14.5 Dia')
console.log('C7/C11/C13: route errors block; balance warnings remain non-blocking; Actual Dia preserved')

const sharedRows = hydrateFabricRows(dyeingContext)
const shared = sharedRows[0].entries[0]
shared.qty = 20
sharedRows[0].entries.push({ ...shared, key: 'other-colour', input_key: 'other-colour', qty: 15 })
assert.deepEqual(fabricWarnings(sharedRows), ['GRN-00008: 35 > source GRN available 34'])
assert.equal(canCalculateFabric(dyeingContext, sharedRows), true)
sharedRows[0].entries[3].qty = 14
assert.deepEqual(fabricWarnings(sharedRows), [], 'exactly available is permitted')
shared.source_stock_per_output = 2
assert.match(fabricWarnings(sharedRows)[0], /54 > source GRN available 34/, 'different output ratios share physical stock')
const acrossRows = [{ ...sharedRows[0], entries: [shared] }, { ...sharedRows[0], fabric_row: 'other-fabric', entries: [{ ...shared, qty: 1 }] }]
assert.equal(fabricWarnings(acrossRows).length, 1, 'source buckets aggregate across fabric rows')
washingRows[0].entries[0].qty = 21
assert.match(fabricWarnings(washingRows)[0], /21 > source GRN available 20/)
assert.equal(canCalculateFabric(washingContext, washingRows), true)
const unavailable = { ...washingContext, source_process: { value: '1::Dyeing', label: 'Dyeing', unavailable: true } }
assert.equal(fabricUnavailableMessage(unavailable), 'Submit an unallocated Dyeing GRN, then reopen Calculate.')
assert.equal(canCalculateFabric(unavailable, washingRows), false)
assert.equal(fabricUnavailableMessage(knittingContext), '')
assert.equal(canCalculateFabric({}, []), false)
console.log('C15/C16: shared-bucket warnings, unavailable guidance and disabled Calculate OK')

function actionPanel(context, commands, refreshContext = async (workOrderName, sourceProcess) => ({ ...context, source_process: { value: sourceProcess } })) {
	const filename = new URL('../frontend/src/departments/fabric-store/WorkOrderActionPanel.vue', import.meta.url)
	const script = readFileSync(filename, 'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1]
		.replace(/^import[\s\S]*?from ["'][^"']+["'];?\s*$/gm, '')
	const bindings = {
		...fabricCalculate, computed, reactive, ref, watch,
		defineProps: () => ({ mode: 'calculate_fabric', workOrder: { name: 'WO-TEST', modified: 'version-1' }, editor: { calculation_contexts: { fabric: context } } }),
		defineEmits: () => () => {},
		executeWorkOrderCommand: async (...arguments_) => commands.push(arguments_),
		getWorkOrderFabricCalculationContext: refreshContext,
	}
	return new Function(...Object.keys(bindings), `${script}\nreturn { initialise, refreshFabricSource, submit, buildPayload, canSubmit, draft, fabricRows, error }`)(...Object.values(bindings))
}

const commands = []
const panel = actionPanel(dyeingContext, commands)
await panel.initialise()
assert.equal(panel.draft.source_process, '0::Knitting')
assert.deepEqual(panel.buildPayload(), buildFabricPayload(dyeingContext, hydrateFabricRows(dyeingContext)))
await panel.submit()
assert.deepEqual(commands[0], ['WO-TEST', 'calculate_fabric', panel.buildPayload(), 'version-1'])
panel.draft.source_process = '1::Dyeing'
assert.equal(panel.buildPayload().source_process, '0::Knitting', 'an unsaved selection cannot change the payload source')
await panel.refreshFabricSource()
assert.equal(panel.buildPayload().source_process, '1::Dyeing')
assert.equal(panel.draft.source_process, '1::Dyeing')
const failedRefreshPanel = actionPanel(dyeingContext, commands, async () => { throw new Error('Source refresh failed') })
await failedRefreshPanel.initialise()
failedRefreshPanel.fabricRows.value[0].entries[0].qty = 12
const previousRows = failedRefreshPanel.fabricRows.value
const previousPayload = failedRefreshPanel.buildPayload()
failedRefreshPanel.draft.source_process = '1::Dyeing'
await failedRefreshPanel.refreshFabricSource()
assert.equal(failedRefreshPanel.draft.source_process, '0::Knitting', 'failed refresh restores the loaded source selection')
assert.equal(failedRefreshPanel.fabricRows.value, previousRows, 'failed refresh retains existing rows and edits')
assert.deepEqual(failedRefreshPanel.buildPayload(), previousPayload, 'failed refresh preserves source and bucket pairing')
assert.equal(failedRefreshPanel.error.value, 'Source refresh failed')
console.log('Source refresh: payload uses the loaded context; failure restores selection and preserves rows')
const noStockPanel = actionPanel(unavailable, commands)
await noStockPanel.initialise()
assert.equal(noStockPanel.canSubmit.value, false)
await noStockPanel.submit()
assert.equal(commands.length, 1, 'unavailable submit never sends a command')
assert.equal(noStockPanel.error.value, '', 'unavailable context creates no error dialog')
const knittingPanel = actionPanel(knittingContext, commands)
await knittingPanel.initialise()
knittingPanel.fabricRows.value[0].entries[0].qty = 0
assert.equal(knittingPanel.canSubmit.value, false)
await knittingPanel.submit()
assert.equal(commands.length, 1, 'orphan yarn submit is refused')
console.log('C5/C7/C16/C17: panel source refresh, command payload and submit guards OK')

function control(name) {
	return { inheritAttrs: false, setup: (properties, { attrs, slots }) => () => Vue.h(name, attrs, [slots.default?.(), slots.footer?.()]) }
}

const modules = {
	'./fabricCalculate.js': fabricCalculate,
	'../../api/fabricStore.js': { executeWorkOrderCommand: async () => {}, getWorkOrderFabricCalculationContext: async () => dyeingContext },
	'../../api/frappe.js': { uploadFile: async () => {} },
	'../../components/common/DateField.vue': control('DateField'),
	'../../components/common/LinkField.vue': control('LinkField'),
	'../../components/documents/DocumentErrorDialog.vue': control('DocumentErrorDialog'),
}
for (const name of ['Button', 'Checkbox', 'Dialog', 'InputNumber', 'InputText', 'Message', 'Select', 'Skeleton', 'Textarea']) {
	modules[`primevue/${name.toLowerCase()}`] = control(name)
}
const component = loadComponent('frontend/src/departments/fabric-store/WorkOrderActionPanel.vue', modules)

async function renderPanel(context) {
	const properties = Vue.reactive({ visible: false, mode: 'calculate_fabric', workOrder: { name: 'WO-TEST' }, editor: { calculation_contexts: { fabric: context } } })
	const root = mountComponent(component, properties)
	properties.visible = true
	await Vue.nextTick()
	return root
}

function renderedText(root) {
	return findNodes(root, () => true).map((node) => node.text).join(' ')
}

function calculateButton(root) {
	return findNodes(root, (node) => node.type === 'Button' && node.props.label === 'Calculate')[0]
}

const renderedKnitting = await renderPanel(knittingContext)
const renderedInputs = findNodes(renderedKnitting, (node) => node.type === 'InputNumber')
assert.equal(renderedInputs.length, 6, 'two routes each render cloth and two yarn controls')
assert.ok(renderedInputs.every((input) => input.props['max-fraction-digits'] === 2), 'cloth and yarn controls show Desk Float precision')
console.log('Precision: cloth and yarn controls display at most two decimal places')
assert.match(renderedText(renderedKnitting), /Program 328 · Ordered 0 · Balance 328/)
assert.match(renderedText(renderedKnitting), /Total · 84.21 Kg/)
const clothInput = renderedInputs[0]
const yarnInput = renderedInputs[1]
yarnInput.props['onUpdate:modelValue'](20)
await Vue.nextTick()
assert.match(renderedText(renderedKnitting), /Total · 85.89 Kg/, 'totals react to manual yarn edits')
clothInput.props['onUpdate:modelValue'](400)
await Vue.nextTick()
assert.match(renderedText(renderedKnitting), /400 > balance 328/)
assert.equal(calculateButton(renderedKnitting).props.disabled, false, 'balance warning leaves Calculate enabled')
clothInput.props['onUpdate:modelValue'](0)
yarnInput.props['onUpdate:modelValue'](1)
await Vue.nextTick()
assert.match(renderedText(renderedKnitting), /Enter the expected cloth quantity/)
assert.equal(calculateButton(renderedKnitting).props.disabled, true)
assert.equal(clothInput.props.invalid, true)
const renderedDyeing = await renderPanel(dyeingContext)
assert.match(renderedText(renderedDyeing), /14.5 Dia \(actual, for 14 Dia\)/)
assert.match(renderedText(renderedDyeing), /GRN-00008 · row 1 · 20 Kg available/)
const renderedUnavailable = await renderPanel(unavailable)
assert.match(renderedText(renderedUnavailable), /No predecessor stock available/)
assert.match(renderedText(renderedUnavailable), /Submit an unallocated Dyeing GRN, then reopen Calculate\./)
assert.equal(calculateButton(renderedUnavailable).props.disabled, true)
assert.equal(findNodes(renderedUnavailable, (node) => node.type === 'DocumentErrorDialog')[0].props.message, '')
console.log('C9-C11/C13/C16: rendered route inputs, reactive totals, warnings and unavailable banner OK')
console.log('Fabric Calculate tests passed')
