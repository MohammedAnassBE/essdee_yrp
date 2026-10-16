#!/usr/bin/env node
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { Vue, createTestRenderer, findNodes, loadComponent } from './helpers/vue_renderer.mjs'
import * as editorHelpers from '../frontend/src/departments/merch/ipd/ipdEditor.js'
import * as gridHelpers from '../frontend/src/components/common/entryGrid.js'
import * as garmentGrids from '../frontend/src/departments/merch/ipd/sections/garmentGrids.js'
import * as packing from '../frontend/src/departments/merch/ipd/sections/packingSection.js'
import * as documentValues from '../frontend/src/utils/documentValues.js'
import * as focus from '../frontend/src/departments/merch/ipd/ipdFocus.js'
import * as bomFetch from '../frontend/src/departments/merch/ipd/ipdBomFetch.js'
import * as tabs from '../frontend/src/departments/merch/ipd/ipdTabs.js'
import { useSectionFocus } from '../frontend/src/departments/merch/ipd/sections/sectionFocus.js'

const base = 'frontend/src/departments/merch/ipd/'
const key = Symbol('editor')
const blank = { render: () => null }
// Only platform controls are substituted: IpdFields, FormField, notices and EntryGrid are real.
const control = kind => ({
	props: { inputId: String, modelValue: {}, options: Array, showClear: Boolean }, emits: ['update:modelValue'],
	render() {
		return Vue.h(kind, {
			...this.$attrs, id: this.inputId, value: this.modelValue, options: this.options,
			showClear: this.showClear, onChoose: value => this.$emit('update:modelValue', value),
		})
	},
})
const modules = {
	'primevue/button': { render() { return Vue.h('button', this.$attrs, this.$attrs.label) } },
	'primevue/inputtext': control('text-control'), 'primevue/inputnumber': control('number-control'),
	'primevue/select': control('select-control'), 'primevue/toggleswitch': control('check-control'),
	'primevue/textarea': blank, './DateField.vue': blank, './DateTimeField.vue': blank,
	'./TimeField.vue': blank, './LinkField.vue': blank,
	'../../utils/documentValues.js': documentValues,
	'../useIpdEditor.js': { IPD_EDITOR_KEY: key }, '../ipdEditor.js': editorHelpers,
	'./entryGrid.js': gridHelpers, './garmentGrids.js': garmentGrids,
	'./packingSection.js': packing, './sectionFocus.js': { useSectionFocus },
}
modules['../../../../components/common/EntryGrid.vue'] = loadComponent('frontend/src/components/common/EntryGrid.vue', {
	...modules, vue: { ...Vue, withDirectives: node => node },
})
const Packing = loadComponent(`${base}sections/IpdPackingSection.vue`, modules)
const modes = ['', 'Size Ratio Packing', 'Size Wise Packing']
const description = 'Size Ratio Packing: one box mixes sizes in a ratio that sums to Packing Combo. Size Wise Packing: each size is packed in its own box with its own pieces per box.'
const seed = {
	packing_attribute: 'Colour', auto_calculate: 0, based_on_other_attribute_mapping: 0,
	packing_mode: '', packing_combo: 3, packing_attribute_no: 1,
	packing_attribute_details: [{ name: 'colour-1', attribute_value: 'Black', quantity: 3 }],
	packing_size_details: [{ name: 'size-1', attribute_value: 'M', quantity: 2 }],
	packing_assortment_json: { assortment_attributes: ['Size'], boxes: [{ separator_value: 'Box', rows: [{ Size: 'M', qty: 1 }] }] },
}
const flush = async () => { await Vue.nextTick(); await Vue.nextTick() }
const text = node => node.type === 'comment' ? '' : node.text + node.children.map(text).join('')
const nodes = (view, predicate) => findNodes(view.root, predicate)
const input = (view, name) => nodes(view, node => node.props.id === `ipd-edit-${name}`)[0]
const grids = view => nodes(view, node => node.props.role === 'grid').map(node => node.props['aria-label'])
const fact = (view, label) => nodes(view, node => node.type === 'dt' && text(node) === label)[0]?.parent.children.find(node => node.type === 'dd')
const mounted = []
function mount(values = {}, readonly = false, extra = {}) {
	const draft = Vue.reactive({ ...structuredClone(seed), ...structuredClone(values) })
	const patches = []
	const valueCalls = [], queuedGrids = []
	function setValue(field, value, { skipGrids } = {}) {
		valueCalls.push({ field, value: structuredClone(value), skipGrids })
		draft[field] = value
		queuedGrids.push(...editorHelpers.gridsForChange([field]).filter(grid => !skipGrids?.has(grid)))
	}
	const editor = {
		draft, readonly, context: {}, fields: {}, gridErrors: () => ({}), registerFocus: () => () => {},
		gridDrift: { packing_sizes: { error: 'SIZE NOTICE' }, packing_assortment: { error: 'ASSORTMENT NOTICE' } },
		setValues(patch) {
			patches.push(structuredClone(patch))
			for (const [field, value] of Object.entries(patch)) setValue(field, value)
		},
		setValue(field, value, options) { patches.push({ [field]: structuredClone(value) }); setValue(field, value, options) }, ...extra,
	}
	const root = { type: 'root', text: '', props: {}, children: [] }
	const app = createTestRenderer().createApp({ setup() {
		Vue.provide(key, editor)
		return () => Vue.h(Packing, { part: 'values', sectionKey: 'packing' })
	} })
	app.mount(root)
	const view = { root, app, draft: editor.draft, patches, valueCalls, queuedGrids, editor }
	mounted.push(app)
	return view
}

const previousDocument = globalThis.document, previousWindow = globalThis.window
globalThis.document = { activeElement: null, getElementById: () => null }
globalThis.window = { removeEventListener() {} }
try {
	// C2–C5, C8–C10: real editable and readonly renders across all Desk conditions.
	for (const readonly of [false, true]) for (const basedOn of [0, 1]) for (const mode of modes) for (const auto of [0, 1]) {
		const view = mount({ based_on_other_attribute_mapping: basedOn, packing_mode: mode, auto_calculate: auto }, readonly)
		const ratio = basedOn === 1 && mode === 'Size Ratio Packing'
		const assortment = basedOn === 1 && mode === ''
		assert.deepEqual(grids(view), [
			...(!auto ? ['Packing Attribute Details'] : []),
			...(ratio ? ['Packing Size Details'] : []), ...(assortment ? ['Box assortment'] : []),
		])
		assert.equal(text(view.root).includes('SIZE NOTICE'), ratio)
		assert.equal(text(view.root).includes('ASSORTMENT NOTICE'), assortment)
		assert.equal(text(view.root).includes('Size wise packing: one piece per box'), false)
		assert.equal(text(view.root).includes('Auto calculate is on:'), Boolean(auto))
		if (readonly) {
			assert.equal(text(fact(view, 'Based on Other Attribute Mapping')), basedOn ? 'Yes' : 'No')
			assert.equal(Boolean(fact(view, 'Packing Mode')), Boolean(basedOn))
			if (basedOn) assert.equal(text(fact(view, 'Packing Mode')), mode || '—')
		} else {
			assert.equal(input(view, 'based_on_other_attribute_mapping').type, 'check-control')
			assert.equal(Boolean(input(view, 'packing_mode')), Boolean(basedOn))
			if (basedOn) assert.equal(input(view, 'packing_mode').props.value, mode)
		}
		for (const title of grids(view)) assert.ok(nodes(view, node => node.type === 'strong' && text(node) === title).length)
		assert.deepEqual(nodes(view, node => node.type === 'button' && ['Fill down', 'Paste', 'Clear'].includes(text(node))), [])
	}
	assert.deepEqual(grids(mount({ packing_attribute_details: [] })), [], 'C8: no selected values means no quantity grid')
	for (const readonly of [false, true]) {
		const empty = mount({ based_on_other_attribute_mapping: 1, packing_assortment_json: null }, readonly)
		assert.ok(text(empty.root).includes('ASSORTMENT NOTICE'), 'C5: empty assortment retains its notice')
		assert.equal(grids(empty).includes('Box assortment'), false)
	}

	// C1: check and select follow the chips and quantity grid in document order.
	const order = mount({ based_on_other_attribute_mapping: 1, packing_mode: 'Size Ratio Packing' })
	assert.deepEqual(nodes(order, node =>
		(node.type === 'label' && ['Auto Calculate', 'Based on Other Attribute Mapping', 'Packing Mode'].includes(text(node).trim())) ||
		node.type === 'legend' || (node.type === 'strong' && grids(order).includes(text(node))),
	).map(node => text(node).trim()), ['Auto Calculate', 'Colour values in one box', 'Packing Attribute Details', 'Based on Other Attribute Mapping', 'Packing Mode', 'Packing Size Details'])
	assert.doesNotMatch(readFileSync(`${base}sections/IpdPackingSection.vue`, 'utf8'), /SelectButton/)

	// C6: toggling through FormField preserves every mode and its stored size rows.
	for (const mode of modes) for (const auto of [0, 1]) {
		const view = mount({ packing_mode: mode, auto_calculate: auto })
		const sizes = structuredClone(seed.packing_size_details)
		for (const checked of [true, false]) {
			input(view, 'based_on_other_attribute_mapping').props.onChoose(checked)
			await flush()
			assert.equal(view.draft.based_on_other_attribute_mapping, Number(checked))
			assert.equal(view.draft.packing_mode, mode)
			assert.deepEqual(view.draft.packing_size_details, sizes)
			assert.ok(Object.keys(view.patches.at(-1)).every(field => ['based_on_other_attribute_mapping', 'packing_combo', 'packing_attribute_no'].includes(field)))
		}
	}

	// A1/C6: checkbox changes skip size sync for sparse rows and obsolete quantities.
	for (const sizes of [
		seed.packing_size_details,
		[...seed.packing_size_details, { name: 'old-size', attribute_value: 'XL', quantity: 7 }],
	]) {
		const view = mount({ based_on_other_attribute_mapping: 1, packing_mode: 'Size Ratio Packing', packing_size_details: sizes })
		const mapping = ['S', 'M', 'L']
		for (const checked of [false, true]) {
			view.valueCalls.length = 0
			view.queuedGrids.length = 0
			input(view, 'based_on_other_attribute_mapping').props.onChoose(checked)
			await flush()
			assert.equal(view.draft.based_on_other_attribute_mapping, Number(checked))
			assert.equal(view.draft.packing_mode, 'Size Ratio Packing')
			assert.ok(view.valueCalls.length > 0, 'checkbox applies changes through setValue')
			for (const call of view.valueCalls) {
				assert.deepEqual(call.skipGrids, new Set(['packing_sizes']), `${call.field} skips only packing_sizes`)
			}
			assert.deepEqual(view.queuedGrids, ['packing_assortment', 'panel_wise_consumption'], 'other dependent grids still refresh')
			// Apply any queued size refresh using the real merge, as the editor would.
			if (view.queuedGrids.includes('packing_sizes')) {
				view.draft.packing_size_details = editorHelpers.mergeGrid('packing_sizes', mapping, view.draft.packing_size_details).value
			}
			assert.deepEqual(view.draft.packing_size_details, sizes, 'no added zero rows or dropped obsolete quantities')
		}
	}

	// C4, C7: explicit Size Wise changes clear rows; clearing Select saves a literal empty string.
	const switcher = mount({ based_on_other_attribute_mapping: 1, packing_mode: 'Size Ratio Packing' })
	input(switcher, 'packing_mode').props.onChoose('Size Wise Packing'); await flush()
	assert.equal(switcher.draft.packing_combo, 1)
	assert.deepEqual(switcher.draft.packing_size_details, [])
	assert.equal(input(switcher, 'packing_mode').props.showClear, true, 'FormField makes the blank choice available via clear')
	input(switcher, 'packing_mode').props.onChoose(null); await flush()
	assert.equal(switcher.draft.packing_mode, '')
	assert.equal(switcher.patches.at(-1).packing_mode, '')
	assert.ok(grids(switcher).includes('Box assortment'))

	// C7: context (including the current payload nesting), metadata and fallback all use Desk choices.
	for (const extra of [
		{}, { context: { packing_modes: modes } }, { context: { options: { packing_modes: modes.slice(1) } } },
		{ fields: { packing_mode: { options: modes.join('\n'), description: 'Live Desk field description.' } } },
	]) {
		const view = mount({ based_on_other_attribute_mapping: 1 }, false, extra)
		// FormField filters the leading blank option and exposes it using show-clear.
		assert.deepEqual(input(view, 'packing_mode').props.options, modes.slice(1))
		assert.equal(input(view, 'packing_mode').props.showClear, true)
		const help = extra.fields?.packing_mode.description || description
		assert.equal(text(view.root).split(help).length - 1, 1, 'Desk description appears once below Packing Mode')
	}
	for (const basedOn of [0, 1]) for (const auto of [0, 1]) for (const mode of modes) {
		assert.equal(packing.isComboDerived({ based_on_other_attribute_mapping: basedOn, auto_calculate: auto, packing_mode: mode }), basedOn ? Boolean(mode) : !auto)
	}

	// Exercise the existing editor grid sync and save boundary with the real composable.
	let stored = { ...structuredClone(seed), based_on_other_attribute_mapping: 1, packing_mode: 'Size Ratio Packing', packing_combo: 2 }
	const payload = () => ({ record: { name: 'QA Packing', modified: 'today' }, capabilities: { edit: { allowed: true } }, values: structuredClone(stored) })
	const saved = [], requests = []
	const hookModules = {
		vue: Vue, 'primevue/usetoast': { useToast: () => ({ add() {} }) },
		'vue-router': { useRoute: () => ({ hash: '#packing_tab' }), useRouter: () => ({ replace() {} }) },
		'../../../router/listDocumentNavigation.js': { preserveListNavigationState() {} },
		'../merchViews.js': { MERCH_ROUTES: {}, ipdEditRoute() {}, ipdRoute() {} },
		'./ipdEditor.js': editorHelpers, './ipdFocus.js': focus, './ipdTabs.js': tabs, './ipdBomFetch.js': bomFetch,
		'../../../api/merch.js': {
			getIpdEditor: async () => payload(), checkIpd: async () => ({ problems: [] }),
			saveIpd: async patch => { saved.push(structuredClone(patch)); stored = { ...stored, ...patch }; return payload() },
			getIpdGrids: async (name, patch, wanted) => {
				requests.push(wanted)
				const next = { ...stored, ...patch }
				return { grids: { packing_sizes: Number(next.based_on_other_attribute_mapping) && next.packing_mode === 'Size Ratio Packing' ? ['S', 'M', 'L'] : null } }
			},
		},
	}
	const hookSource = readFileSync(`${base}useIpdEditor.js`, 'utf8')
		.replace(/import\s+([\s\S]*?)\s+from\s+["']([^"']+)["'];?/g, (_, names, path) => `const ${names.trim()} = modules[${JSON.stringify(path)}];`)
		.replaceAll('export ', '')
	const { useIpdEditor } = new Function('modules', `${hookSource}\nreturn { useIpdEditor }`)(hookModules)
	let hook
	const host = createTestRenderer().createApp({ setup() { hook = useIpdEditor('QA Packing'); return () => null } })
	host.mount({ type: 'root', text: '', props: {}, children: [] }); mounted.push(host)
	await flush()
	assert.equal(hook.loadError.value, '')
	const live = mount({}, false, { ...hook.api })
	input(live, 'based_on_other_attribute_mapping').props.onChoose(false); await flush()
	await hook.save()
	assert.deepEqual(saved.at(-1), { based_on_other_attribute_mapping: 0, packing_combo: 3 }, 'C6: unticked save preserves mode and size rows at the save API')
	assert.equal(stored.packing_mode, 'Size Ratio Packing')
	assert.deepEqual(stored.packing_size_details, seed.packing_size_details)
	input(live, 'based_on_other_attribute_mapping').props.onChoose(true); await flush()
	input(live, 'packing_mode').props.onChoose('Size Wise Packing'); await flush()
	input(live, 'packing_mode').props.onChoose('Size Ratio Packing'); await flush()
	await new Promise(resolve => setTimeout(resolve, 450)); await flush()
	assert.ok(requests.some(wanted => wanted.includes('packing_sizes')), 'C7: mode change queues packing size sync')
	assert.deepEqual(hook.draft.packing_size_details.map(row => [row.attribute_value, row.quantity]), [['S', 0], ['M', 0], ['L', 0]])
	assert.equal(hook.actionError.value, '')
} finally {
	for (const app of mounted) app.unmount()
	globalThis.document = previousDocument
	globalThis.window = previousWindow
}
console.log('IPD Packing C1–C10: Desk visibility/order, FormField controls, readonly facts, preserved toggles/save, blank mode, derived values, size sync and toolbar removal passed')
