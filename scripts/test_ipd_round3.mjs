#!/usr/bin/env node
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { Vue, createTestRenderer, findNodes, loadComponent, mountComponent } from './helpers/vue_renderer.mjs'
import { createFocusRegistry, goToProblem, gridFocusKey } from '../frontend/src/departments/merch/ipd/ipdFocus.js'
import { useSectionFocus } from '../frontend/src/departments/merch/ipd/sections/sectionFocus.js'
import * as tabs from '../frontend/src/departments/merch/ipd/ipdTabs.js'
import * as ipdEditor from '../frontend/src/departments/merch/ipd/ipdEditor.js'
import * as grids from '../frontend/src/departments/merch/ipd/sections/garmentGrids.js'
import * as entryGrid from '../frontend/src/components/common/entryGrid.js'
import * as attributes from '../frontend/src/departments/merch/ipd/sections/attributeValues.js'
import * as packing from '../frontend/src/departments/merch/ipd/sections/packingSection.js'
import * as rename from '../frontend/src/departments/merch/ipd/sections/clothRename.js'
import * as bomMapping from '../frontend/src/departments/merch/ipd/sections/bomMapping.js'

const base = 'frontend/src/departments/merch/ipd/'
const samples = JSON.parse(readFileSync('scripts/fixtures/ipd_samples.json', 'utf8'))
const key = Symbol('editor')
const blank = { render: () => null }
const modules = {
	'primevue/button': blank, 'primevue/inputtext': blank, 'primevue/select': blank, 'primevue/selectbutton': blank,
	'primevue/dialog': { inheritAttrs: false, render() { return this.$slots.default?.() } }, 'primevue/message': blank,
	'../useIpdEditor.js': { IPD_EDITOR_KEY: key }, '../ipdEditor.js': ipdEditor, './ipdEditor.js': ipdEditor,
	'./ipdTabs.js': tabs, './garmentGrids.js': grids, './attributeValues.js': attributes, './packingSection.js': packing,
	'./clothRename.js': rename, './sectionFocus.js': { useSectionFocus }, './sections.css': {},
	'./bomMapping.js': bomMapping, './BomMappingDialog.vue': blank, '../../../../components/common/FormField.vue': {
		props: ['inputId'], render() { return Vue.h('span', { id: this.inputId, tabindex: -1 }) },
	},
	'../../../../components/common/LinkField.vue': blank, './LinkField.vue': blank, './entryGrid.js': entryGrid,
}
const EntryGrid = loadComponent('frontend/src/components/common/EntryGrid.vue', modules)
modules['../../../../components/common/EntryGrid.vue'] = EntryGrid
const component = name => loadComponent(`${base}sections/${name}.vue`, modules)
const Cutting = component('IpdCuttingSection'), Stitching = component('IpdStitchingSection')
const Processes = component('IpdProcessesSection'), Accessories = component('IpdAccessoriesSection'), Packing = component('IpdPackingSection')
const Settings = component('IpdSettingsSection')
const previousDocument = globalThis.document, previousWindow = globalThis.window
globalThis.document = { activeElement: null, getElementById: () => null }
globalThis.window = { removeEventListener() {} }
const flush = async () => { await Vue.nextTick(); await Vue.nextTick() }
function mountParts(parts, draft, readonly) {
	const registry = createFocusRegistry()
	const api = { draft: Vue.reactive(draft), readonly, fields: {}, context: {}, grids: {}, gridErrors: () => ({}), registerFocus: registry.registerFocus }
	const root = { type: 'root', text: '', props: {}, children: [] }
	const app = createTestRenderer().createApp({
		setup() {
			Vue.provide(key, api)
			return () => Vue.h('div', parts.map(([type, part, sectionKey]) => Vue.h(type, { part, sectionKey })))
		},
	})
	app.mount(root)
	document.getElementById = id => findNodes(root, node => node.props.id === id)[0] || null
	for (const element of findNodes(root, () => true)) {
		element.focus = function () { document.activeElement = this }
		element.scrollIntoView = () => {}
		element.setAttribute = (name, value) => { element.props[name] = value }
	}
	for (const table of findNodes(root, node => node.props.role === 'grid')) table.querySelector = selector => {
		const [, row, col] = selector.match(/data-row="(\d+)"\]\[data-col="(\d+)"/)
		return findNodes(table, node => node.props['data-row'] === Number(row) && node.props['data-col'] === Number(col))[0]
	}
	for (const choices of findNodes(root, node => node.type === 'fieldset')) choices.querySelector = selector =>
		findNodes(choices, node => node.type === 'input' && (selector === 'input' || !node.props.disabled))[0] || null
	return { root, app, api, registry }
}
async function focus(view, problem, expectedTitle) {
	document.activeElement = null
	assert.equal(await goToProblem(problem, {
		async jumpTo() { await flush() },
		focusFirstControl() { throw Error('must never focus a different field') },
	}, view.registry.focusProblem), true)
	await flush()
	const cell = document.activeElement
	assert.equal(cell?.props.role, 'gridcell', problem.field)
	assert.equal(cell.props['data-row'], 0, problem.field)
	assert.equal(cell.props['data-col'], 0, problem.field)
	let table = cell
	while (table && table.props.role !== 'grid') table = table.parent
	assert.equal(table.props['aria-label'], expectedTitle, problem.field)
}
try {
	for (const readonly of [false, true]) {
		const draft = { ...structuredClone(samples.standard.values), enable_panel_wise_consumption_matrix: 0, ipd_processes: [{ name: 'p1', process_name: 'Cutting', in_stage: 'Cut Panel' }], packing_attribute_details: [{ attribute_value: 'Black', quantity: 1 }], based_on_other_attribute_mapping: 0, auto_calculate: 0 }
		const view = mountParts([
			[Cutting, 'cloths', 'cutting'], [Cutting, 'consumption', 'cutting'], [Cutting, 'mapping', 'cutting'],
			[Stitching, 'details', 'stitching'], [Stitching, 'items', 'stitching'], [Stitching, 'combination', 'stitching'],
			[Accessories, 'bom', 'accessories'], [Processes, 'general', 'processes'], [Processes, 'embellishment', 'processes'],
			[Packing, 'details', 'packing'], [Packing, 'values', 'packing'],
		], draft, readonly)
		for (const [section, field, title] of [
			['cutting', 'cutting_items_json', 'Consumption per piece'], ['cutting', 'cutting_cloths_json', 'Cloth by combination'],
			['cutting', 'cloth_detail', 'Cloth Detail'], ['stitching', 'stiching_item_details', 'Stiching Item Details'],
			['stitching', 'stiching_item_detail', 'Colour of each panel'], ['processes', 'ipd_processes', 'IPD Processes'],
			['accessories', 'item_bom', 'Item BOM'], ['packing', 'packing_attribute_details', 'Packing Attribute Details'],
		]) {
			assert.equal(gridFocusKey(field, draft), field)
			await focus(view, { section, field, row_key: null }, title)
		}
		view.app.unmount()
		const ratio = mountParts([[Packing, 'details', 'packing'], [Packing, 'values', 'packing']], { ...structuredClone(samples.set_size_ratio.values), based_on_other_attribute_mapping: 1, packing_mode: 'Size Ratio Packing' }, readonly)
		await focus(ratio, { section: 'packing', field: 'packing_size_details', row_key: null }, 'Packing Size Details')
		assert.equal(findNodes(ratio.root, node => node.props.role === 'grid' && node.props['aria-label'] === 'Box assortment').length, 0, 'ratio packing has no assortment')
		assert.equal(findNodes(ratio.root, node => node.type === 'button' && ['Fill down', 'Paste', 'Clear'].includes(node.props.label)).length, 0, 'packing grids have no toolbar actions')
		ratio.app.unmount()
		const panelDraft = { ...structuredClone(samples.panel_grouped.values), enable_panel_wise_consumption_matrix: 1 }
		const panel = mountParts([[Cutting, 'cloths', 'cutting'], [Cutting, 'consumption', 'cutting'], [Cutting, 'mapping', 'cutting']], panelDraft, readonly)
		assert.equal(gridFocusKey('cutting_items_json', panelDraft), 'panel_wise_consumption_matrix_json')
		assert.equal(gridFocusKey('cutting_cloths_json', panelDraft), 'panel_wise_cloth_mapping_json')
		for (const field of ['cutting_items_json', 'panel_wise_consumption_matrix_json']) await focus(panel, { section: 'cutting', field, row_key: null }, panelDraft.panel_wise_consumption_matrix_json.panels[0].panel_value)
		for (const field of ['cutting_cloths_json', 'panel_wise_cloth_mapping_json']) await focus(panel, { section: 'cutting', field, row_key: null }, panelDraft.panel_wise_cloth_mapping_json.panels[0].panel_value || 'All panels')
		panel.app.unmount()
		const empty = mountParts([[Accessories, 'accessories', 'accessories'], [Accessories, 'stitching', 'accessories'], [Processes, 'general', 'processes']], {}, readonly)
		assert.ok(findNodes(empty.root, node => node.text === 'No accessory items.').length)
		assert.ok(findNodes(empty.root, node => node.text === 'Accessory colours appear after accessory items are added.').length)
		document.activeElement = null
		assert.equal(await goToProblem({ section: 'processes', field: 'ipd_processes', row_key: null }, { async jumpTo() {}, focusFirstControl() { throw Error('wrong control') } }, empty.registry.focusProblem), false)
		assert.equal(document.activeElement, null, 'an absent grid must never focus a bare section')
		empty.app.unmount()
		// Exercise the actual conditional grids and focus hooks, not a stubbed failure.
		for (const packing_attribute of ['', 'Colour']) {
			const emptyPacking = mountParts([[Packing, 'details', 'packing'], [Packing, 'values', 'packing'], [Settings, 'packing', 'packing']], {
				packing_attribute, auto_calculate: 1, packing_attribute_details: [{ attribute_value: 'Black', quantity: 1 }],
			}, readonly)
			assert.equal(findNodes(emptyPacking.root, node => node.props.role === 'grid').length, 0)
			for (const field of ['packing_attribute_details', 'packing_size_details']) {
				document.activeElement = null
				const visited = []
				assert.equal(await goToProblem({ section: 'packing', field, row_key: null, message: 'Packing Attribute is required' }, {
					async jumpTo(tab) { visited.push(tab); await flush() },
					focusFirstControl() { throw Error('wrong packing control') },
				}, emptyPacking.registry.focusProblem), true, `${field}: grid not rendered -> fallback`)
				assert.equal(visited.at(-1), packing_attribute ? 'packing_tab' : 'advance_settings_tab')
				const expected = packing_attribute
					? findNodes(emptyPacking.root, node => node.type === (readonly ? 'fieldset' : 'input'))[0]
					: document.getElementById('ipd-edit-packing_attribute')
				assert.equal(Vue.toRaw(document.activeElement), expected, `${field}: related control takes focus`)
				if (!packing_attribute && !readonly) assert.equal(document.activeElement.type, 'span')
			}
			emptyPacking.app.unmount()
		}
	}
} finally { globalThis.document = previousDocument; globalThis.window = previousWindow }

// Field ownership wins over the legacy server section, including settings and BOM.
const changes = [{ section: 'item', field: 'description', source: 'Old', current: 'New' }, { section: 'cutting', field: 'packing_process' }, { section: 'accessories', field: 'item_bom' }, { section: 'cutting', field: 'unknown_server_field' }]
assert.deepEqual(changes.map(tabs.tabLabel), ['Item Details', 'Advance Settings', 'Item Details', 'Cutting'])
for (const name of ['IpdCopyBanner', 'IpdChangesDialog']) {
	const type = loadComponent(`${base}${name}.vue`, modules)
	const root = mountComponent(type, { source: name === 'IpdCopyBanner' ? { name: 'Source' } : 'Source', changes, visible: true })
	const text = findNodes(root, () => true).map(node => node.text).join(' ')
	assert.match(text, /Item Details/); assert.match(text, /Advance Settings/); assert.match(text, /Cutting/)
	assert.doesNotMatch(text, /Item & versions|Attributes & values|Cutting & cloth|Accessories & BOM|Processes & embellishment|Review & approve/)
	if (name === 'IpdChangesDialog') assert.equal(findNodes(root, node => node.type === 'th')[0].text, 'Tab')
}
// Drive the actual tab panel directive through empty, loaded and cleared content.
const directives = []
const Panel = loadComponent(`${base}IpdTabPanel.vue`, { vue: { ...Vue, withDirectives(vnode, entries) { directives.push(...entries.map(([directive]) => directive)); return vnode } } })
mountComponent(Panel, { tab: { sections: [{ heading: '', parts: [] }] }, doc: {}, panelId: 'panel', labelledby: 'tab' })
assert.equal(directives.length, 1)
const previousObserver = globalThis.MutationObserver
let refresh, observed, disconnected = false
try {
	globalThis.MutationObserver = class {
		constructor(callback) { refresh = callback }
		observe(element, options) { observed = { element, options } }
		disconnect() { disconnected = true }
	}
	const content = { textContent: '  ', querySelector: () => null }
	const empty = { hidden: true, style: { display: 'none' } }
	const element = { firstElementChild: content, lastElementChild: empty }
	directives[0].mounted(element)
	assert.equal(empty.hidden, false, 'a visible empty section must display its empty state')
	assert.equal(empty.style.display, '')
	assert.equal(observed.element, content)
	assert.equal(observed.options.subtree, true)
	content.textContent = 'Loaded grid title'; refresh()
	assert.equal(empty.hidden, true, 'async section content replaces the empty state')
	assert.equal(empty.style.display, 'none', 'inline display wins over the shared help-text class')
	for (const ownEmptyText of ['No accessory items.', 'Accessory colours appear after accessory items are added.']) {
		content.textContent = ownEmptyText; refresh()
		assert.equal(empty.hidden, true, 'a section-specific empty line is content')
		assert.equal(empty.style.display, 'none', 'never show both empty lines')
	}
	content.textContent = ''; refresh()
	assert.equal(empty.hidden, false, 'removing the final row/content restores the empty state')
	assert.equal(empty.style.display, '')
	content.querySelector = () => ({ type: 'input' }); refresh()
	assert.equal(empty.hidden, true, 'an input is meaningful content even before it contains text')
	directives[0].unmounted(element)
	assert.equal(disconnected, true)
} finally { globalThis.MutationObserver = previousObserver }
console.log('IPD Rounds 3–4: editor/record grid focus, absent-grid control fallbacks, exclusive empty states and Tab header passed')
