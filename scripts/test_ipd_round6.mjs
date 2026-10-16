import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { Vue, createTestRenderer, findNodes, loadComponent } from './helpers/vue_renderer.mjs'
import * as focus from '../frontend/src/departments/merch/ipd/ipdFocus.js'
import * as bomFetch from '../frontend/src/departments/merch/ipd/ipdBomFetch.js'
import * as tabs from '../frontend/src/departments/merch/ipd/ipdTabs.js'
import * as editorHelpers from '../frontend/src/departments/merch/ipd/ipdEditor.js'
import * as gridHelpers from '../frontend/src/components/common/entryGrid.js'
import * as garmentGrids from '../frontend/src/departments/merch/ipd/sections/garmentGrids.js'
import * as attributeValues from '../frontend/src/departments/merch/ipd/sections/attributeValues.js'
import * as packing from '../frontend/src/departments/merch/ipd/sections/packingSection.js'
import * as rename from '../frontend/src/departments/merch/ipd/sections/clothRename.js'
import * as bomMapping from '../frontend/src/departments/merch/ipd/sections/bomMapping.js'
import * as clothGrids from '../frontend/src/departments/merch/ipd/cloth/clothGrids.js'
import * as clothTable from '../frontend/src/departments/merch/ipd/cloth/useClothTable.js'
import { useSectionFocus } from '../frontend/src/departments/merch/ipd/sections/sectionFocus.js'

const base = 'frontend/src/departments/merch/ipd/'
const blank = { render: () => null }
const control = { props: ['modelValue', 'inputId', 'label'], emits: ['update:modelValue'], render() {
	return Vue.h('input', { ...this.$attrs, id: this.inputId, value: this.modelValue, onInput: value => this.$emit('update:modelValue', value) })
} }
const route = Vue.reactive({ hash: '#item_details_tab', query: {} })
const router = { async replace(value) { if (value.hash) route.hash = value.hash } }
const messages = []
const toast = { add: message => messages.push(message.detail) }
let saveCalls = 0
let saveError = ''
let serverProblems = []
const payload = { record: { name: 'QA IPD', modified: 'today' }, capabilities: { edit: { allowed: true } }, values: {
	item: 'Vest', description: 'Old', is_cloth_item: 0, packing_attribute: '', is_set_item: 1,
	item_attributes: [{ name: 'size', attribute: 'Size', mapping: 'sizes' }, { name: 'colour', attribute: 'Colour', mapping: 'colours' }],
	cloth_detail: [{ name: 'cloth-1', name1: 'Body', required_gsm: 100 }, { name: 'cloth-2', name1: 'Rib', required_gsm: 200 }],
	cutting_items_json: { attributes: ['Panel', 'Dia', 'Weight'], items: [{ Panel: 'Front', Dia: '30', Weight: 0.1 }] },
	ipd_processes: [{ name: 'process-1', process_name: 'Cutting', in_stage: 'Cut', out_stage: 'Cut' }],
}, context: { cutting_attribute_choices: ['Size', 'Colour'] } }
let editorPayload = payload
const api = {
	getIpdEditor: async () => structuredClone(editorPayload), checkIpd: async () => ({ problems: serverProblems }),
	saveIpd: async () => { saveCalls += 1; if (saveError) throw new Error(saveError); return structuredClone(payload) },
}
const modules = {
	'primevue/button': { render() { return Vue.h('button', this.$attrs, this.$attrs.label) } },
	'primevue/inputtext': control, 'primevue/select': control, 'primevue/selectbutton': control,
	'primevue/checkbox': control, 'primevue/toggleswitch': control, 'primevue/dialog': blank, 'primevue/message': blank,
	'primevue/usetoast': { useToast: () => toast },
	'vue-router': { useRoute: () => route, useRouter: () => router },
	'../../../api/merch.js': api,
	'../../../router/listDocumentNavigation.js': { preserveListNavigationState: () => ({}) },
	'../merchViews.js': { MERCH_ROUTES: {}, ipdEditRoute: () => ({}), ipdRoute: () => ({}) },
	'./ipdEditor.js': editorHelpers, '../ipdEditor.js': editorHelpers,
	'./ipdTabs.js': tabs, './ipdFocus.js': focus, '../ipdFocus.js': focus, './ipdBomFetch.js': bomFetch,
	'./entryGrid.js': gridHelpers, '../../../components/common/entryGrid.js': gridHelpers, './garmentGrids.js': garmentGrids, './sections/garmentGrids.js': garmentGrids,
	'./attributeValues.js': attributeValues, './packingSection.js': packing, './clothRename.js': rename,
	'./clothGrids.js': clothGrids, './useClothTable.js': { ...clothTable, useClothSection(props) {
		const editor = Vue.inject(hook.IPD_EDITOR_KEY)
		return { editor, readonly: Vue.computed(() => Boolean(props.readonly || editor.readonly)), cloth: Vue.computed(() => editor.context?.cloth || {}) }
	} }, './sectionFocus.js': { useSectionFocus },
	'../../../../components/common/FormField.vue': control, '../../../../components/common/LinkField.vue': control,
	'./LinkField.vue': blank, './bomMapping.js': bomMapping, './BomMappingDialog.vue': blank, './IpdAttributeChips.vue': blank,
}
// Load the actual composable with API/router boundaries substituted, as for SFCs.
const hookSource = readFileSync(`${base}useIpdEditor.js`, 'utf8')
	.replace(/import\s+([\s\S]*?)\s+from\s+["']([^"']+)["'];?/g, (_, names, path) => `const ${names.trim()} = modules[${JSON.stringify(path)}];`)
	.replaceAll('export ', '')
const hook = new Function('modules', `${hookSource}\nreturn { useIpdEditor, IPD_EDITOR_KEY }`)({ vue: Vue, ...modules })
modules['../useIpdEditor.js'] = hook
modules['./useIpdEditor.js'] = hook
// Supply v-model through its compiled update handler; the renderer has no native DOM directives.
const EntryGrid = loadComponent('frontend/src/components/common/EntryGrid.vue', { ...modules, vue: { ...Vue, withDirectives: node => node } })
modules['../../../../components/common/EntryGrid.vue'] = EntryGrid
const section = name => loadComponent(`${base}sections/${name}.vue`, modules)
const Attributes = section('IpdAttributesSection')
const Cutting = section('IpdCuttingSection')
const Settings = section('IpdSettingsSection')
const Item = section('IpdItemSection')
const componentByKey = { attributes: Attributes, cutting: Cutting, settings: Settings, item: Item, processes: section('IpdProcessesSection') }
for (const [key, name] of Object.entries({ packing: 'IpdPackingSection', set_item: 'IpdSetItemSection', stitching: 'IpdStitchingSection', accessories: 'IpdAccessoriesSection' })) componentByKey[key] = section(name)
for (const [key, name] of Object.entries({ yarn_ratio: 'IpdYarnRatioSection', fabric_routes: 'IpdFabricRoutesSection', fabric_processes: 'IpdFabricProcessesSection', compacting: 'IpdCompactingSection' })) componentByKey[key] = loadComponent(`${base}cloth/${name}.vue`, modules)
modules['./ipdSectionRegistry.js'] = { preloadSectionComponents() {}, sectionComponent: key => componentByKey[key] || blank }
// Empty-state observation is covered in Round 3; omit the browser observer here.
modules['./IpdTabPanel.vue'] = loadComponent(`${base}IpdTabPanel.vue`, { vue: { ...Vue, withDirectives: node => node } })
const Sections = loadComponent(`${base}IpdSections.vue`, modules)

let root
const previousDocument = globalThis.document, previousWindow = globalThis.window, previousHTMLElement = globalThis.HTMLElement
const animationFrames = []
globalThis.window = { addEventListener() {}, removeEventListener() {}, requestAnimationFrame(callback) { animationFrames.push(callback) } }
globalThis.HTMLElement = class { static [Symbol.hasInstance](node) { return typeof node?.focus === 'function' } }
function matches(node, selector) {
	if (selector === 'h2' || selector === 'input') return node.type === selector
	if (selector === 'input:not(:disabled)') return node.type === 'input' && !node.props.disabled
	if (selector.startsWith('.')) return String(node.props.class).split(' ').includes(selector.slice(1))
	const tag = selector.match(/^[a-z]+/)?.[0]
	return (!tag || node.type === tag) && [...selector.matchAll(/\[([^=\]]+)(?:="([^"]*)")?\]/g)]
		.every(([, key, value]) => value == null ? node.props[key] != null : String(node.props[key]) === value)
}
function wireDOM() {
	for (const node of findNodes(root, () => true)) {
		node.dataset = Object.fromEntries(Object.entries(node.props).filter(([key]) => key.startsWith('data-')).map(([key, value]) => [key.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase()), value]))
		node.focus = () => { document.activeElement = node }
		node.id = node.props.id || ''
		node.isConnected = true
		node.blur = () => { document.activeElement = null }
		node.scrollIntoView = () => {}
		node.getBoundingClientRect = () => ({ left: 0, right: 100 })
		node.setAttribute = (key, value) => { node.props[key] = value }
		node.contains = target => { while (target) { if (target === node) return true; target = target.parent } return false }
		node.querySelectorAll = selector => { wireDOM(); return findNodes(node, candidate => candidate !== node && matches(candidate, selector)) }
		node.querySelector = selector => node.querySelectorAll(selector)[0] || null
		node.closest = selector => { let target = node; while (target && !matches(target, selector)) target = target.parent; return target }
		node.dispatchEvent = event => node.props[`on${event.type[0].toUpperCase()}${event.type.slice(1)}`]?.(event)
	}
}
globalThis.document = { activeElement: null, getElementById(id) { wireDOM(); return findNodes(root, node => node.props.id === id)[0] || null } }
const flush = async () => { for (let index = 0; index < 5; index++) await Vue.nextTick(); wireDOM() }
function mount(render, setup) {
	root = { type: 'root', props: {}, children: [] }
	const app = createTestRenderer().createApp({ setup() { setup?.(); return render } })
	app.mount(root)
	wireDOM()
	return app
}
const text = node => findNodes(node, () => true).map(child => child.text || '').join(' ')
function cell(table, row, col) { return table.querySelector(`td[data-row="${row}"][data-col="${col}"]`) }
function paste(table, row, col, value) {
	cell(table, row, col).props.onMousedown({ button: 0, preventDefault() {} })
	table.props.onPaste({ preventDefault() {}, clipboardData: { getData: () => value } })
}
async function typeCell(table, row, col, value) {
	cell(table, row, col).props.onMousedown({ button: 0, preventDefault() {} })
	table.props.onKeydown({ key: 'F2', preventDefault() {} })
	await flush()
	const input = cell(table, row, col).querySelector('input')
	input.props['onUpdate:modelValue'](value) // Ctrl+A replaces the whole input.
	input.props.onKeydown({ key: 'Enter', preventDefault() {}, stopPropagation() {} })
	await flush()
}
async function selectTab(key) {
	findNodes(root, node => node.props.role === 'tab' && node.props['aria-controls']?.endsWith(`panel-${key}`))[0].props.onClick()
	await flush()
}
const saveAction = () => findNodes(root, node => node.type === 'actions')[0].props.actions.find(action => action.key === 'save')
async function clickSave() {
	findNodes(root, node => node.props['aria-label'] === 'Save IPD')[0].focus()
	await saveAction().command()
	await flush()
}
async function closeErrorDialog(target, method = 'OK') {
	const dialog = findNodes(root, node => node.type === 'dialog')[0]
	assert.ok(dialog, 'the error dialog is open')
	assert.equal(dialog.props.header, 'Item Production Detail could not be completed')
	assert.equal(document.activeElement.props.label, 'OK', 'focus stays on OK while the dialog is open')
	if (method === 'Esc') dialog.props.onKeydown({ key: 'Escape' })
	else findNodes(dialog, node => node.type === 'button' && (method === 'X' ? node.props['aria-label'] === 'Close' : node.props.label === 'OK'))[0].props.onClick()
	await flush()
	for (let frame = 0; frame < 5; frame++) {
		for (const callback of animationFrames.splice(0)) callback()
		await flush()
	}
	assert.equal(findNodes(root, node => node.type === 'dialog').length, 0)
	assert.ok(document.activeElement === target, `${method}: focus returns to the problem cell after all dialog restoration callbacks (active: ${document.activeElement?.type} ${JSON.stringify(document.activeElement?.dataset)})`)
}

try {
	// New IPD: attributes come from the Item; saved value cards remain absent.
	const registry = focus.createFocusRegistry()
	const draft = Vue.reactive({ item_attributes: [{ name: 'saved', attribute: 'Size', mapping: 'sizes' }] })
	const editor = Vue.reactive({ draft, readonly: false, isNew: true, context: {}, registerFocus: registry.registerFocus,
		setValue(field, value) { draft[field] = value },
	})
	let app = mount(() => Vue.h(Attributes, { sectionKey: 'attributes' }), () => Vue.provide(hook.IPD_EDITOR_KEY, editor))
	await flush()
	assert.equal(document.getElementById('ipd-edit-new-attribute'), null)
	assert.equal(findNodes(root, node => node.type === 'button' && node.props.label === 'Add attribute').length, 0)
	assert.equal(findNodes(root, node => node.props.class === 'ipd-chip-cards').length, 0)
	assert.match(text(root), /Attribute values are copied from the Item when you create the IPD/)
	assert.equal(await registry.focusProblem({ field: 'item_attributes', row_key: 'Size' }), true)
	assert.equal(document.activeElement.props.id, 'ipd-edit-item_attributes')
	app.unmount()

	// Real sections in both editor and record modes, including a later attribute row.
	for (const readonly of [false, true]) {
		route.hash = '#item_details_tab'
		messages.length = 0
		const recordRegistry = focus.createFocusRegistry()
		const values = Vue.reactive(structuredClone(payload.values))
		const recordEditor = { ...editor, draft: values, readonly, isNew: false, fields: {}, context: payload.context,
			registerFocus: recordRegistry.registerFocus, gridErrors: () => ({}),
		}
		const frame = Vue.ref(null)
		app = mount(() => Vue.h(Sections, { ref: frame, tabs: tabs.IPD_TABS, doc: values, readonly }), () => Vue.provide(hook.IPD_EDITOR_KEY, recordEditor))
		await flush()
		for (const problem of [
			{ field: 'item_attributes', row_key: 'Colour', column: 'mapping' },
			{ field: 'item_attributes', row: 'Colour', column: 'attribute' },
			{ field: 'item_attributes', row_key: 'colour', column: 'mapping' },
		]) {
			assert.equal(await focus.goToProblem({ section: 'attributes', ...problem }, frame.value, recordRegistry.focusProblem), true)
			assert.equal(document.activeElement.dataset.attribute, 'Colour')
		}
		for (const field of ['is_set_item', 'set_item_detail']) {
			assert.equal(await focus.goToProblem({ section: 'set_item', field, row_key: 'Red', column: 'Top' }, frame.value, recordRegistry.focusProblem), true)
			assert.equal(route.hash, '#advance_settings_tab')
			assert.equal(document.activeElement.props.id, 'ipd-edit-packing_attribute')
			assert.equal(messages.at(-1), 'Set Item is hidden until Packing Attribute is set.')
		}
		assert.equal(await focus.goToProblem({ section: 'cutting', field: 'cutting_attributes' }, frame.value, recordRegistry.focusProblem), true)
		assert.equal(route.hash, '#cutting_tab')
		assert.equal(document.activeElement.props.id, 'ipd-edit-cutting_attributes')
		assert.equal(await recordRegistry.focusProblem({ field: 'item_attributes', row_key: 'Missing' }), true)
		assert.equal(document.activeElement.props.id, 'ipd-edit-item_attributes')
		for (const problem of [
			{ section: 'cutting', field: 'cloth_detail', row_key: 'missing', column: 'required_gsm' },
			{ section: 'cutting', field: 'cloth_detail', row_key: 'cloth-2', column: 'missing' },
		]) {
			assert.equal(await focus.goToProblem(problem, frame.value, recordRegistry.focusProblem), false)
			assert.equal(document.activeElement.type, 'h2', 'an unknown cell focuses the section heading')
			assert.match(messages.at(-1), /Cell not located/)
		}
		app.unmount()
	}
	assert.match(tabs.problemNavigation({ field: 'cloth_detail' }, tabs.IPD_TABS, {}, { isNew: true }).note, /hidden until the IPD is saved/)
	assert.equal(tabs.problemNavigation({ field: 'fabric_processes' }, tabs.IPD_TABS, {}, { isNew: false }).target.field, 'is_cloth_item')

	// Actual editor Save handler + composable + cached tabs + real Cutting grid.
	let currentEditor
	// Model PrimeVue's show/hide transition and opener restoration; use the real error dialog.
	const Dialog = {
		props: ['visible', 'header'], emits: ['show', 'hide', 'after-hide', 'update:visible'],
		setup(props, { emit, slots }) {
			let opener
			Vue.watch(() => props.visible, async visible => {
				if (visible) {
					opener = document.activeElement
					await Vue.nextTick(); wireDOM(); emit('show')
				} else {
					emit('hide'); opener?.focus()
					window.requestAnimationFrame(() => emit('after-hide'))
				}
			})
			const close = () => emit('update:visible', false)
			return () => props.visible ? Vue.h('dialog', { header: props.header, onKeydown: event => { if (event.key === 'Escape') close() } }, [
				Vue.h('button', { 'aria-label': 'Close', onClick: close }), slots.default?.(), slots.footer?.(),
			]) : null
		},
	}
	const ErrorDialog = loadComponent('frontend/src/components/documents/DocumentErrorDialog.vue', { ...modules, 'primevue/dialog': Dialog })
	const editorModules = { ...modules,
		'./useIpdEditor.js': { ...hook, useIpdEditor(name) { currentEditor = hook.useIpdEditor(name); return currentEditor } },
		'./IpdSections.vue': Sections,
		'../../fabric-store/FabricDocumentWorkspace.vue': { props: ['loading', 'error'], render() { return Vue.h('main', [
			...(this.loading ? [] : [this.$slots['header-actions']?.(), this.$slots.matrix?.()]),
			Vue.h(ErrorDialog, { message: this.error, title: 'Item Production Detail could not be completed' }),
		]) } },
		'../../../components/documents/DocumentActionStrip.vue': { props: ['actions'], render() { return Vue.h('actions', { actions: this.actions }, [Vue.h('button', { 'aria-label': 'Save IPD' })]) } },
		'../../../components/documents/DocumentErrorDialog.vue': ErrorDialog,
	}
	for (const path of ['./IpdChangesDialog.vue', './IpdChecksRail.vue', './IpdCopyBanner.vue', './IpdCopyDialog.vue', './IpdIdentity.vue',
		'../../../components/documents/DocumentConfirmationDialog.vue']) editorModules[path] = blank
	const Editor = loadComponent(`${base}IpdEditor.vue`, editorModules)
	route.hash = '#cutting_tab'
	app = mount(() => Vue.h(Editor, { ipdId: 'QA IPD' }))
	await flush()
	// Exact browser sequence, before Item Details has ever mounted its own grids.
	let consumption = findNodes(root, node => node.props.role === 'grid' && node.props['aria-label'] === 'Consumption per piece')[0]
	await typeCell(consumption, 0, 1, 'abc')
	assert.equal(cell(consumption, 0, 1).props['aria-invalid'], true)
	assert.equal(cell(consumption, 0, 1).props.title, 'abc is not a number.')
	assert.equal(currentEditor.isDirty.value, false, 'invalid text does not enter the draft')
	assert.equal(saveAction().disabled, true, 'Save can stay disabled until another field changes')
	await selectTab('item_details_tab')
	assert.equal(currentEditor.firstInvalidCell.value?.field, 'cutting_items_json', 'a valid grid mounting must not erase a cached grid’s errors')
	document.getElementById('ipd-edit-description').props.onInput('Changed description')
	await flush()
	assert.equal(saveAction().disabled, false)
	await clickSave()
	assert.equal(saveCalls, 0, 'F2/Enter invalid input blocks saveIpd')
	assert.equal(route.hash, '#cutting_tab')
	assert.match(currentEditor.actionError.value, /^Cutting:.*highlighted cell/)
	for (const method of ['OK', 'Esc', 'X']) {
		if (method !== 'OK') { await selectTab('item_details_tab'); await clickSave() }
		assert.equal(route.hash, '#cutting_tab')
		assert.equal(saveCalls, 0)
		await closeErrorDialog(cell(consumption, 0, 1), method)
	}
	await typeCell(consumption, 0, 1, '0.1')
	const table = findNodes(root, node => node.props.role === 'grid' && node.props['aria-label'] === 'Cloth Detail')[0]
	assert.ok(table)
	paste(table, 1, 2, 'invalid-number'); await flush()
	assert.equal(currentEditor.firstInvalidCell.value.field, 'cloth_detail')
	assert.equal(currentEditor.firstInvalidCell.value.row_key, 'cloth-2')
	assert.equal(currentEditor.firstInvalidCell.value.column, 'required_gsm')
	assert.equal(cell(table, 1, 2).props['aria-invalid'], true)
	route.hash = '#item_details_tab'; await flush()
	const description = document.getElementById('ipd-edit-description')
	description.props.onInput('Changed description'); await flush()
	await clickSave()
	assert.equal(saveCalls, 0, 'invalid client input blocks the server write')
	assert.equal(route.hash, '#cutting_tab')
	assert.match(currentEditor.actionError.value, /^Cutting:.*highlighted cell/)
	await closeErrorDialog(cell(table, 1, 2))
	// A second invalid cell is retained after the first is corrected.
	paste(table, 0, 2, 'also-invalid'); await flush()
	paste(table, 1, 2, '250'); await flush()
	assert.equal(currentEditor.firstInvalidCell.value.row_key, 'cloth-1')
	paste(table, 0, 2, '150'); await flush()
	assert.equal(currentEditor.firstInvalidCell.value, null)
	// Browser regression: F2 in the consumption grid, then mount valid grids in another tab.
	consumption = findNodes(root, node => node.props.role === 'grid' && node.props['aria-label'] === 'Consumption per piece')[0]
	await typeCell(consumption, 0, 1, 'abc')
	assert.equal(cell(consumption, 0, 1).props.title, 'abc is not a number.')
	assert.equal(currentEditor.firstInvalidCell.value.field, 'cutting_items_json')
	route.hash = '#item_details_tab'; await flush()
	assert.equal(currentEditor.firstInvalidCell.value?.field, 'cutting_items_json', 'mounting a valid grid must not clear another grid’s errors')
	await clickSave()
	assert.equal(saveCalls, 0)
	assert.equal(route.hash, '#cutting_tab')
	assert.match(currentEditor.actionError.value, /^Cutting:/)
	await closeErrorDialog(cell(consumption, 0, 1))
	// Correcting a different invalid grid cannot clear this grid's report.
	paste(table, 0, 2, 'invalid-gsm'); await flush()
	await typeCell(consumption, 0, 1, '0.1')
	assert.equal(currentEditor.firstInvalidCell.value?.field, 'cloth_detail')
	paste(table, 0, 2, '100'); await flush()
	assert.equal(currentEditor.firstInvalidCell.value, null)
	await saveAction().command(); await flush()
	assert.equal(saveCalls, 1, 'correcting all invalid cells allows a normal save')
	// Server save failures keep the check's target through every dialog dismissal path.
	saveError = 'The server rejected this IPD.'
	serverProblems = [{ section: 'cutting', field: 'cutting_items_json', row_key: 'Front', column: 'Weight' }]
	for (const method of ['OK', 'Esc', 'X']) {
		await selectTab('item_details_tab')
		document.getElementById('ipd-edit-description').props.onInput(`Server failure ${method}`)
		await flush(); await clickSave()
		assert.equal(route.hash, '#cutting_tab')
		assert.equal(currentEditor.actionError.value, saveError)
		await closeErrorDialog(cell(consumption, 0, 1), method)
	}
	saveError = ''; serverProblems = []
	app.unmount()
	saveCalls = 0

	const gridValues = {
		...payload.values, packing_attribute: 'Colour', primary_item_attribute: 'Size', set_item_attribute: 'Part', stiching_attribute: 'Panel',
		packing_attribute_details: [{ attribute_value: 'Black', quantity: 1 }], packing_size_details: [{ attribute_value: 'M', quantity: 1 }],
		packing_assortment_json: { assortment_attributes: ['Size'], boxes: [{ separator_value: 'Box', rows: [{ Size: 'M', qty: 1 }] }] },
		set_item_detail: { attributes: ['Top'], values: [{ major_attribute: 'Black', val: { Top: 'Black' } }] },
		stiching_item_details: [{ stiching_attribute_value: 'Front', quantity: 1 }],
		stiching_item_detail: { attributes: ['Front'], values: [{ major_attribute: 'Black', val: { Front: 'Black' } }] },
		marker_groups: [['Front']], emblishment_details_json: { Print: ['Front'] },
		item_bom: [{ name: 'bom-1', item: 'Thread', qty_of_product: 1, qty_of_bom_item: 1 }],
		cutting_cloths_json: { attributes: ['Panel', 'Cloth'], items: [{ Panel: 'Front', Cloth: 'Body' }] },
		accessory_clothtype_json: { Rib: 'Top' },
		cloth_accessory_json: { attributes: ['Accessory', 'Dia', 'Weight'], items: [{ Accessory: 'Rib', Dia: '30', Weight: 0.1 }] },
		stiching_accessory_json: { items: [{ accessory: 'Rib', major_colour: 'Black', accessory_colour: 'Black', cloth_type: 'Body' }] },
		panel_wise_consumption_matrix_json: { packing_values: ['Black'], panels: [{ group_id: 'Front', panel_value: 'Front', rows: [{ primary_value: 'M', values: { Black: { dia: '30', weight: 0.1 } } }] }] },
		panel_wise_cloth_mapping_json: { cloth_options: ['Body'], panels: ['Front', 'Back'].map(group_id => ({ group_id, panel_value: group_id, packing_values: ['Black'], rows: [{ values: { Black: { cloth: 'Body' } } }] })) },
		fabric_processes: [{ sequence: 10, quantity_ratio: 1 }], fabric_value_mappings: [{ sequence: 10, mapping_index: 1 }],
		yarn_ratio_details: [{ yarn_item: 'Cotton', ratio: 100 }], colour_yarn_recipes: [{ colour: 'Black', yarn_item: 'Cotton', ratio: 100 }],
		fabric_routes: [{ finished_colour: 'Black', finished_dia: '30' }], compacting_reference_details: [{ colour: 'Black', input_dia: '30' }],
	}
	// Every editable EntryGrid in the actual sections, with sibling grids mounted and cached.
	const gridCases = [
		['item_bom', 'Item BOM', 2], ['ipd_processes', 'IPD Processes', 2],
		['packing_attribute_details', 'Packing Attribute Details', 0],
		['packing_size_details', 'Packing Size Details', 0, { based_on_other_attribute_mapping: 1, packing_mode: 'Size Ratio Packing' }],
		['packing_assortment_json', 'Box assortment', 0, { based_on_other_attribute_mapping: 1, packing_mode: '' }],
		['set_item_detail', 'Colour of each part', 0], ['stiching_item_details', 'Stiching Item Details', 1],
		['stiching_item_detail', 'Colour of each panel', 0], ['marker_groups', 'Panels cut together', 0],
		['emblishment_details_json', 'Embellishment', 0], ['cloth_detail', 'Cloth Detail', 2],
		['cutting_items_json', 'Consumption per piece', 1], ['cutting_cloths_json', 'Cloth by combination', 0],
		['accessory_clothtype_json', 'Accessory names', 0], ['cloth_accessory_json', 'Accessory consumption', 1],
		['stiching_accessory_json', 'Accessory colour and cloth', 1],
		['panel_wise_consumption_matrix_json', 'Front', 1, { enable_panel_wise_consumption_matrix: 1 }],
		['panel_wise_cloth_mapping_json', 'Back', 0, { enable_panel_wise_consumption_matrix: 1 }],
		['fabric_processes', 'Fabric processes', 4, { is_cloth_item: 1 }],
		['fabric_value_mappings', 'Fabric value mappings', 1, { is_cloth_item: 1 }],
		['yarn_ratio_details', 'Yarns and ratios', 1, { is_cloth_item: 1 }],
		['fabric_routes', 'Fabric routes', 0, { is_cloth_item: 1 }],
		['compacting_reference_details', 'Compacting references', 0, { is_cloth_item: 1 }],
	]
	for (const [field, label, column, extra] of gridCases) {
		editorPayload = { ...payload, values: { ...gridValues, ...extra } }
		const targetTab = tabs.problemTab({ field })
		route.hash = `#${targetTab}`
		app = mount(() => Vue.h(Editor, { ipdId: 'QA IPD' })); await flush()
		const grid = findNodes(root, node => node.props.role === 'grid' && node.props['aria-label'] === label)[0]
		assert.ok(grid, `${field}: real grid is mounted`)
		if (field.startsWith('packing_')) {
			const section = grid.parent.parent
			assert.equal(findNodes(section, node => node.type === 'button' && ['Fill down', 'Paste', 'Clear'].includes(node.props.label)).length, 0, `${field}: packing toolbar actions removed`)
		}
		paste(grid, 0, column, 'abc'); await flush()
		assert.equal(cell(grid, 0, column).props['aria-invalid'], true, field)
		assert.equal(currentEditor.firstInvalidCell.value?.field, field)
		const otherTab = targetTab === 'item_details_tab' ? (extra?.is_cloth_item ? 'compacting_reference_tab' : 'cutting_tab') : 'item_details_tab'
		await selectTab('item_details_tab')
		document.getElementById('ipd-edit-description').props.onInput('Changed description')
		await flush()
		await selectTab(otherTab)
		assert.equal(currentEditor.firstInvalidCell.value?.field, field, `${field}: errors survive sibling mounts and deactivation`)
		await clickSave()
		assert.equal(saveCalls, 0, `${field}: no saveIpd request`)
		assert.equal(route.hash, `#${targetTab}`)
		assert.ok(currentEditor.actionError.value.startsWith(`${tabs.tabLabel({ field })}:`), field)
		await closeErrorDialog(cell(grid, 0, column))
		app.unmount()
	}
	editorPayload = payload

	// Reordered columns keep paste, fill and named focus attached to their fields.
	for (const isSet of [false, true]) {
		const values = Vue.reactive({ is_set_item: Number(isSet), set_item_attribute: 'Part', stiching_item_details: [
			{ name: 'front', stiching_attribute_value: 'Front', quantity: 1, category: 'Body', is_default: 0 },
			{ name: 'back', stiching_attribute_value: 'Back', quantity: 2, category: 'Body', is_default: 0 },
		] })
		const registry = focus.createFocusRegistry()
		const localEditor = { ...editor, draft: values, isNew: false, registerFocus: registry.registerFocus, gridErrors: () => ({}),
			context: { attributes: [{ attribute: 'Part', values: ['Top'] }], options: { stitching_categories: ['Body', 'Main Panel'] } },
			setValue(field, value) { values[field] = value },
		}
		app = mount(() => Vue.h(componentByKey.stitching, { part: 'items', sectionKey: 'stitching' }), () => Vue.provide(hook.IPD_EDITOR_KEY, localEditor))
		const grid = findNodes(root, node => node.props.role === 'grid')[0]
		assert.deepEqual(findNodes(grid, node => node.type === 'th' && node.props.scope === 'col').map(text).filter(label => label.trim() !== 'Remove'), [
			'Stiching Attribute Value', ...(isSet ? ['Set Item Attribute Value'] : []), 'Quantity', 'Category', ...(isSet ? ['Is Default'] : []),
		])
		paste(grid, 0, 0, isSet ? 'Top\t3\tMain Panel\t1' : '3\tMain Panel'); await flush()
		assert.equal(values.stiching_item_details[0].quantity, 3)
		assert.equal(values.stiching_item_details[0].category, 'Main Panel')
		if (isSet) {
			assert.equal(values.stiching_item_details[0].set_item_attribute_value, 'Top')
			assert.equal(values.stiching_item_details[0].is_default, 1)
		}
		const quantityColumn = isSet ? 1 : 0
		cell(grid, 1, quantityColumn).props.onMousedown({ button: 0, preventDefault() {} })
		grid.props.onKeydown({ key: 'd', ctrlKey: true, preventDefault() {} }); await flush()
		assert.equal(values.stiching_item_details[1].quantity, 2, 'IPD grids have no Ctrl+D fill down')
		assert.equal(findNodes(grid.parent, node => node.type === 'button' && ['Fill down', 'Fill right', 'Paste', 'Clear'].includes(node.props.label)).length, 0, 'stitching grid has no toolbar tools')
		for (const [column, key] of (isSet ? ['set_item_attribute_value', 'quantity', 'category', 'is_default'] : ['quantity', 'category']).entries()) {
			assert.equal(await registry.focusProblem({ field: 'stiching_item_details', row_key: 'back', column: key }), true)
			await flush()
			assert.ok(document.activeElement === cell(grid, 1, column), `${key}: named focus follows Desk column order`)
		}
		assert.deepEqual(values.stiching_item_details.map(row => row.name), ['front', 'back'])
		app.unmount()
	}
	{
		const values = Vue.reactive({ fabric_routes: [
			{ name: 'route-1', finished_colour: 'Black', finished_dia: '30', knitting_output_colour: 'White', use_dyed_yarn: 0, knitting_output_dia: '30' },
			{ name: 'route-2', finished_colour: 'Black', finished_dia: '30', knitting_output_colour: 'White', use_dyed_yarn: 0, knitting_output_dia: '30' },
		] })
		const registry = focus.createFocusRegistry()
		const localEditor = { ...editor, draft: values, registerFocus: registry.registerFocus, gridErrors: () => ({}),
			context: { cloth: { colour_values: ['Black', 'White'], dia_values: ['30', '32'] } },
			setValue(field, value) { values[field] = value },
		}
		app = mount(() => Vue.h(componentByKey.fabric_routes, { sectionKey: 'fabric_routes' }), () => Vue.provide(hook.IPD_EDITOR_KEY, localEditor))
		const grid = findNodes(root, node => node.props.role === 'grid')[0]
		paste(grid, 0, 0, 'Black\t30\tWhite\t1\t32'); await flush()
		assert.equal(values.fabric_routes[0].use_dyed_yarn, 1)
		assert.equal(values.fabric_routes[0].knitting_output_dia, '32')
		cell(grid, 1, 4).props.onMousedown({ button: 0, preventDefault() {} })
		grid.props.onKeydown({ key: 'd', ctrlKey: true, preventDefault() {} }); await flush()
		assert.equal(values.fabric_routes[1].knitting_output_dia, '32')
		assert.equal(values.fabric_routes[1].use_dyed_yarn, 0, 'dia fill does not change the adjacent check')
		for (const [column, key] of [[3, 'use_dyed_yarn'], [4, 'knitting_output_dia']]) {
			assert.equal(await registry.focusProblem({ field: 'fabric_routes', row_key: 'route-2', column: key }), true)
			await flush()
			assert.ok(document.activeElement === cell(grid, 1, column), `${key}: named focus follows Desk column order`)
		}
		assert.deepEqual(values.fabric_routes.map(row => row.name), ['route-1', 'route-2'])
		app.unmount()
	}

	// Labels come from Desk metadata, including any property-setter overrides.
	const customFields = JSON.parse(readFileSync('essdee_yrp/fixtures/custom_field.json', 'utf8'))
	const overrides = JSON.parse(readFileSync('essdee_yrp/fixtures/property_setter.json', 'utf8'))
	function deskLabel(doctype, field, fallback) {
		return overrides.find(row => row.doc_type === doctype && row.field_name === field && row.property === 'label')?.value || fallback
	}
	function childFields(doctype) {
		const name = doctype.toLowerCase().replaceAll(' ', '_')
		const path = [`essdee_yrp/essdee_yrp/doctype/${name}/${name}.json`, `../yrp/yrp/yrp/doctype/${name}/${name}.json`].find(existsSync)
		const metadata = JSON.parse(readFileSync(path, 'utf8'))
		let order = [...metadata.field_order]
		const fields = new Map(metadata.fields.map(field => [field.fieldname, { ...field }]))
		for (const field of customFields.filter(row => row.dt === doctype)) {
			fields.set(field.fieldname, { ...field })
			order = order.filter(name => name !== field.fieldname)
			const after = order.indexOf(field.insert_after)
			order.splice(after < 0 ? order.length : after + 1, 0, field.fieldname)
		}
		for (const setter of overrides.filter(row => row.doc_type === doctype)) {
			if (setter.property === 'field_order') {
				const prescribed = JSON.parse(setter.value)
				for (const [index, name] of order.entries()) {
					if (prescribed.includes(name)) continue
					const after = fields.get(name).insert_after || order[index - 1]
					const position = prescribed.indexOf(after)
					prescribed.splice(position < 0 ? prescribed.length : position + 1, 0, name)
				}
				order = prescribed
			}
			else if (fields.has(setter.field_name)) fields.get(setter.field_name)[setter.property] = setter.value
		}
		return order.filter(name => fields.has(name)).map(name => fields.get(name))
	}
	const labelCases = [
		['IpdPackingSection', 'values', 'packing', { packing_attribute: 'Colour', auto_calculate: 0, packing_attribute_details: [{ attribute_value: 'Black', quantity: 1 }] }, 'SD YRP Item Production Detail Packing Attribute Detail', ['attribute_value', 'quantity']],
		['IpdPackingSection', 'values', 'packing', { ...gridValues, based_on_other_attribute_mapping: 1, packing_mode: 'Size Ratio Packing', primary_item_attribute: 'Garment Size' }, 'SD YRP Item Production Detail Packing Size Detail', ['attribute_value', 'quantity']],
		['IpdStitchingSection', 'items', 'stitching', { stiching_attribute: 'Panel', stiching_item_details: [{ stiching_attribute_value: 'Front', quantity: 1 }] }, 'SD YRP Stiching Item Detail', ['stiching_attribute_value', 'quantity', 'category']],
		['IpdStitchingSection', 'items', 'stitching', gridValues, 'SD YRP Stiching Item Detail', ['stiching_attribute_value', 'set_item_attribute_value', 'quantity', 'category', 'is_default']],
		['IpdCuttingSection', 'cloths', 'cutting', gridValues, 'SD YRP Item Production Detail Cloth Detail', ['name1', 'cloth', 'required_gsm', 'is_bom_item']],
		['IpdAccessoriesSection', 'bom', 'accessories', { ...gridValues, dependent_attribute: 'Stage' }, 'YRP Item BOM', ['item', 'process_name', 'dependent_attribute_value', 'qty_of_product', 'qty_of_bom_item', 'uom', 'based_on_attribute_mapping', 'wastage_pct']],
		['IpdProcessesSection', 'general', 'processes', gridValues, 'YRP IPD Process', ['process_name', 'process_item']], // Stage is intentionally merged.
		['cloth/IpdFabricProcessesSection', '', 'fabric_processes', gridValues, 'SD YRP IPD Fabric Process', ['sequence', 'fabric_process', 'input_item', 'output_item', 'quantity_ratio']],
		['cloth/IpdFabricProcessesSection', '', 'fabric_processes', gridValues, 'SD YRP IPD Fabric Value Mapping', ['sequence', 'mapping_index', 'attribute', 'role', 'from_value', 'to_value']],
		['cloth/IpdFabricRoutesSection', '', 'fabric_routes', gridValues, 'SD YRP IPD Fabric Route', ['finished_colour', 'finished_dia', 'knitting_output_colour', 'use_dyed_yarn', 'knitting_output_dia']],
		['cloth/IpdYarnRatioSection', '', 'yarn_ratio', gridValues, 'SD YRP IPD Yarn Ratio', ['yarn_item', 'ratio']],
		['cloth/IpdYarnRatioSection', '', 'yarn_ratio', gridValues, 'SD YRP IPD Colour Yarn Ratio', ['colour', 'yarn_item', 'yarn_colour', 'ratio']],
		['cloth/IpdCompactingSection', '', 'compacting', { compacting_reference_details: [{ colour: 'Black', input_dia: '30', compacting_dia: '28' }] }, 'SD YRP IPD Compacting Reference', ['colour', 'input_dia', 'compacting_dia', 'notes']],
	]
	for (const [name, part, sectionKey, values, doctype, fields] of labelCases) {
		const Component = name.startsWith('cloth/') ? loadComponent(`${base}${name}.vue`, modules) : section(name)
		app = mount(() => Vue.h(Component, { part, sectionKey }), () => Vue.provide(hook.IPD_EDITOR_KEY, { ...editor, draft: values, context: {}, gridErrors: () => ({}) }))
		const expected = childFields(doctype).filter(field => fields.includes(field.fieldname)).map(field => field.label)
		const columnLabels = grid => findNodes(grid, node => node.type === 'th' && node.props.scope === 'col').map(text)
		const grid = findNodes(root, node => node.props.role === 'grid').find(grid => expected.every(label => columnLabels(grid).includes(label)))
		const headers = columnLabels(grid)
		for (const field of fields) assert.ok(headers.includes(deskLabel(doctype, field, childFields(doctype).find(row => row.fieldname === field).label)), `${name}: ${field}`)
		assert.deepEqual(headers.filter(label => expected.includes(label)), expected, `${name}: columns follow Desk field order`)
		const tableField = childFields('YRP Item Production Detail').find(row => row.fieldtype === 'Table' && row.options === doctype)
		const title = deskLabel('YRP Item Production Detail', tableField.fieldname, tableField.label)
		assert.ok(findNodes(root, node => node.type === 'strong' && node.text === title).length, `${name}: Desk table title ${title}`)
		app.unmount()
	}
	const Fabric = loadComponent(`${base}cloth/IpdFabricProcessesSection.vue`, modules)
	app = mount(() => Vue.h(Fabric, { sectionKey: 'fabric_processes' }), () => Vue.provide(hook.IPD_EDITOR_KEY, { ...editor,
		draft: { fabric_processes: [{ sequence: 1 }], fabric_value_mappings: [{ sequence: 1 }] }, context: {}, gridErrors: () => ({}),
	}))
	for (const field of ['fabric_processes', 'fabric_value_mappings']) {
		const label = customFields.find(row => row.dt === 'YRP Item Production Detail' && row.fieldname === field).label
		assert.ok(findNodes(root, node => node.type === 'strong' && node.text === deskLabel('YRP Item Production Detail', field, label)).length)
	}
	app.unmount()
} finally {
	globalThis.document = previousDocument
	globalThis.window = previousWindow
	globalThis.HTMLElement = previousHTMLElement
}
console.log('IPD Rounds 6–9: Item-owned attributes and card focus, hidden tabs, exact focus after OK/Esc/X for client/server save errors, F2/Enter Save regression, 23 editable grids across cached tabs, Desk metadata labels/order, and reordered paste/fill/focus passed')
