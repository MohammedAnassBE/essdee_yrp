import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import AutoComplete from '../frontend/node_modules/primevue/autocomplete/index.mjs'
import { Vue, createTestRenderer, findNodes, loadComponent } from './helpers/vue_renderer.mjs'
import { handleAutocompleteKey, withAutocompleteCompositionGuard } from '../frontend/src/components/common/autocompleteKeys.js'
import * as editorHelpers from '../frontend/src/departments/merch/ipd/ipdEditor.js'
import * as focus from '../frontend/src/departments/merch/ipd/ipdFocus.js'
import { useSectionFocus } from '../frontend/src/departments/merch/ipd/sections/sectionFocus.js'

const base = 'frontend/src/departments/merch/ipd/sections/'
const key = Symbol('details-editor')
const blank = { render: () => null }
const modules = {
	vue: { ...Vue, withDirectives: node => node },
	'../useIpdEditor.js': { IPD_EDITOR_KEY: key },
	'../ipdEditor.js': editorHelpers,
	'../ipdFocus.js': focus,
	'./sectionFocus.js': { useSectionFocus },
	'primevue/button': { render() { return Vue.h('button', this.$attrs, this.$attrs.label) } },
	'../../../../api/purchase.js': { searchItemAttributeValues: async () => [] },
	'../../../../components/documents/DocumentConfirmationDialog.vue': blank,
	'../../../../components/common/LinkField.vue': {
		props: ['doctype', 'searchHandler', 'showOpenButton'],
		render() { return Vue.h('link-field', { ...this.$attrs, ...this.$props }) },
	},
	'../../../../components/common/FormField.vue': {
		props: ['field', 'inputId', 'modelValue', 'disabled', 'required'],
		render() { return Vue.h('input', { id: this.inputId, field: this.field, disabled: this.disabled, required: this.required, value: this.modelValue }) },
	},
}
const Item = loadComponent(`${base}IpdItemSection.vue`, modules)
const Attributes = loadComponent(`${base}IpdAttributesSection.vue`, modules)
const names = ['primary_item_attribute', 'dependent_attribute', 'tech_pack_version', 'pattern_version', 'copied_from', 'approved_by']
const labels = ['Primary Item Attribute', 'Dependent Attribute', 'Tech Pack Version', 'Pattern Version', 'Copied From', 'Approved By']
const hasClass = (node, name) => String(node.props.class).split(' ').includes(name)
const allText = root => findNodes(root, () => true).map(node => node.text).join(' ')
const nodes = (root, type) => findNodes(root, node => node.type === type)

for (const readonly of [false, true]) {
	for (const isNew of [false, true]) {
		const registry = focus.createFocusRegistry()
		const attributes = ['Stage', 'Panel', 'Colour', 'Size']
		const editor = {
			readonly, isNew, ...registry,
			draft: {
				item: 'Garment', description: 'Full width description', primary_item_attribute: 'Size', dependent_attribute: 'Stage',
				stiching_attribute: 'Panel', packing_attribute: 'Colour',
				item_attributes: attributes.map(attribute => ({ attribute, name: attribute, mapping: `private-mapping-${attribute}` })),
			},
			context: {
				attributes: attributes.map(attribute => ({ attribute, values: [`${attribute} value`] })),
				dependent: { attr_list: { Cut: { attributes: ['Panel'], uom: 'Nos', name: 'Cutting' } } },
			},
		}
		const root = { type: 'root', props: {}, children: [] }
		const app = createTestRenderer().createApp({ setup() {
			Vue.provide(key, editor)
			return () => Vue.h('main', [Vue.h(Item, { sectionKey: 'item' }), Vue.h(Attributes, { sectionKey: 'attributes' })])
		} })
		app.mount(root)
		const row = findNodes(root, node => hasClass(node, 'ipd-item-details-row'))[0]
		const wide = findNodes(root, node => hasClass(node, 'ipd-item-details-wide'))
		assert.equal(row.type, readonly ? 'dl' : 'div')
		assert.equal(wide.length, isNew ? 2 : 1)
		if (readonly) {
			assert.deepEqual(row.children.filter(node => node.type === 'div').map(node => node.props.id), names.map(name => `ipd-edit-${name}`))
			assert.deepEqual(nodes(row, 'dt').map(node => node.text), labels)
			assert.equal(nodes(wide.at(-1), 'dt')[0].text, 'Description')
		} else {
			const inputs = nodes(row, 'input')
			assert.deepEqual(inputs.map(node => node.props.id), names.map(name => `ipd-edit-${name}`))
			assert.deepEqual(inputs.map(node => node.props.field.label), labels)
			for (const input of inputs.slice(0, 2)) {
				assert.equal(input.props.field.fieldtype, 'Select')
				assert.equal(input.props.field.options, attributes.join('\n'))
				assert.equal(input.props.disabled, !isNew)
			}
			assert.ok(inputs.slice(4).every(input => input.props.disabled))
			assert.equal(nodes(wide.at(-1), 'input')[0].props.id, 'ipd-edit-description')
			if (isNew) assert.equal(nodes(wide[0], 'input')[0].props.required, true)
		}
		assert.equal(findNodes(root, node => node.props.id === 'ipd-edit-item').length, Number(isNew))
		assert.equal(findNodes(root, node => node.props.id === 'ipd-edit-approval_status').length, 0)
		const attributeSection = findNodes(root, node => node.props.id === 'ipd-edit-item_attributes')[0]
		assert.equal(nodes(attributeSection, 'table').length, 0)
		assert.doesNotMatch(allText(attributeSection), /Attribute Mapping|private-mapping-|Add attribute|Edited in Desk/)
		assert.equal(findNodes(attributeSection, node => node.props.id === 'ipd-edit-primary_item_attribute' || node.props.id === 'ipd-edit-dependent_attribute').length, 0)
		for (const field of ['additional_cloth', 'stiching_attribute_quantity']) {
			assert.equal(findNodes(attributeSection, node => node.props.id === `ipd-edit-${field}`).length, 1)
		}
		const cards = nodes(attributeSection, 'article')
		assert.equal(cards.length, isNew ? 0 : 4)
		if (isNew) assert.match(allText(attributeSection), /Attribute values are copied from the Item when you create the IPD\./)
		else {
			assert.deepEqual(cards.map(card => card.props['aria-label']), attributes.map(attribute => `${attribute} values`))
			for (const role of ['Primary', 'Dependent', 'Packing', 'Stitching']) assert.ok(allText(attributeSection).includes(role))
			const links = nodes(attributeSection, 'link-field')
			assert.equal(links.length, readonly ? 0 : 3)
			for (const link of links) {
				assert.equal(link.props.doctype, 'Item Attribute Value')
				assert.equal(typeof link.props.searchHandler, 'function')
				assert.equal(link.props.showOpenButton, false)
			}
			assert.equal(nodes(attributeSection, 'datalist').length, 0)
		}
		app.unmount()
	}
}

// Exercise real LinkField validation and PrimeVue keyboard selection on a value card.
const controls = []
const searches = []
const catalogue = { Colour: ['BLACK', 'Bottle Green', 'Bone'], Part: ['Bottom'] }
const autocomplete = {
	extends: AutoComplete,
	props: { unstyled: { default: true } },
	mounted() {
		this.$el.querySelector = () => nodes(this.$el, 'input')[0]
		this.$el.querySelector('input').focus = () => {}
		controls.push(this)
	},
	methods: {
		onKeyDown: AutoComplete.methods.onKeyDown,
		alignOverlay() {}, scrollInView() {},
		hide() { this.overlayVisible = false; this.focusedOptionIndex = -1 },
	},
	render() {
		return Vue.h('autocomplete', {
			value: this.modelValue, 'aria-label': this.ariaLabel,
			onType: text => { this.onInput({ target: { value: text } }); clearTimeout(this.searchTimeout) },
			onSearch: text => this.search({}, text, 'input'),
			onBlur: () => this.onBlur({}),
		}, [Vue.h('input', { ref: 'focusInput', onKeydown: event => this.onKeyDown(event) })])
	},
}
const linkModules = {
	'primevue/autocomplete': autocomplete, 'primevue/button': modules['primevue/button'],
	'./autocompleteKeys.js': { handleAutocompleteKey, withAutocompleteCompositionGuard },
	'../../api/frappe.js': { searchLink: () => { throw new Error('Use the attribute search handler') } },
	'../../router/webDocumentRoutes.js': { webDocumentPath: () => '' },
}
const LinkField = loadComponent('frontend/src/components/common/LinkField.vue', linkModules)
const Chips = loadComponent(`${base}IpdAttributeChips.vue`, {
	...modules,
	'../../../../components/common/LinkField.vue': LinkField,
	'../../../../api/purchase.js': { searchItemAttributeValues: async (attribute, query) => {
		searches.push([attribute, query])
		return catalogue[attribute].filter(label => label.toLowerCase().includes(query.toLowerCase()))
			.map(label => ({ name: `catalogue-${attribute}-${label}`, label }))
	} },
	'../../../../components/documents/DocumentConfirmationDialog.vue': { render() { return Vue.h('confirmation', this.$attrs) } },
})
const chipsSource = readFileSync(`${base}IpdAttributeChips.vue`, 'utf8')
assert.match(chipsSource, /<LinkField[\s\S]*?doctype="Item Attribute Value"[\s\S]*?:search-handler="searchValues"/)
assert.doesNotMatch(chipsSource, /<datalist|<input|function suggest\(/)
assert.match(chipsSource, /@paste\.capture="onPaste"/)
const flush = async () => { for (let i = 0; i < 5; i++) await Vue.nextTick() }
for (const attribute of ['Colour', 'Part']) {
	const props = Vue.reactive({ attribute, values: attribute === 'Colour' ? ['Black'] : [], editable: true })
	const saves = []
	let finishSave
	const root = { type: 'root', props: {}, children: [] }
	const app = createTestRenderer().createApp({ setup() {
		Vue.provide(key, {
			saveAttributeValues: async (attribute, values) => {
				saves.push([attribute, values])
				await new Promise(resolve => { finishSave = resolve })
				props.values = values
			},
			valueUsage: async (attribute, [value]) => ({ [value]: [{ label: 'Packing row 1' }] }),
		})
		return () => Vue.h(Chips, props)
	} })
	app.mount(root)
	const control = controls.at(-1)
	const field = () => nodes(root, 'autocomplete')[0]
	const search = async text => { field().props.onType(text); field().props.onSearch(text); await flush() }
	const enter = async () => {
		const target = control.$el.querySelector('input')
		const event = { key: 'Enter', target, preventDefault() {}, stopPropagation() { this.stopped = true } }
		findNodes(root, node => typeof node.props.onKeydownCapture === 'function')[0].props.onKeydownCapture(event)
		if (!event.stopped) target.props.onKeydown(event)
		await flush()
	}
	assert.equal(control.$parent.$props.doctype, 'Item Attribute Value')
	assert.equal(control.$parent.$props.showOpenButton, false)
	assert.equal(control.placeholder, `+ add ${attribute}`)
	assert.equal(field().props['aria-label'], `Add ${attribute} values`)
	assert.equal(nodes(root, 'datalist').length, 0)
	await search('Bo')
	assert.deepEqual(searches.at(-1), [attribute, 'Bo'])
	assert.deepEqual(control.suggestions.map(row => row.label), attribute === 'Colour' ? ['Bottle Green', 'Bone'] : ['Bottom'])
	assert.equal(control.focusedOptionIndex, 0, 'first suggestion is highlighted')
	const selected = control.suggestions[0].label
	await enter()
	assert.deepEqual(saves, [[attribute, [...props.values, selected]]], 'Enter saves the selected label')
	assert.equal(control.disabled, true)
	assert.match(allText(root), /Saving/)
	await search('Bo')
	assert.ok(!control.suggestions.some(row => row.label === selected), 'pending values are excluded')
	finishSave()
	await flush()
	assert.equal(field().props.value, null, 'LinkField resets after saving')
	assert.equal(control.disabled, false)
	assert.ok(allText(root).includes(selected))
	await search('')
	assert.ok(control.suggestions.every(row => !props.values.some(value => value.toLowerCase() === row.label.toLowerCase())), 'saved values are excluded without regard to case')
	for (const finish of ['Enter', 'blur']) {
		await search('does not exist')
		if (finish === 'Enter') await enter()
		else { field().props.onBlur(); await flush() }
		assert.equal(saves.length, 1, `${finish} on free text adds nothing`)
		assert.match(nodes(root, 'small').find(node => node.props.role === 'alert')?.text || '', /Pick (one|a value) from the list/)
	}
	nodes(root, 'button').find(node => node.props['aria-label'] === `Remove ${selected}`).props.onClick()
	await flush()
	const confirmation = nodes(root, 'confirmation')[0]
	assert.equal(confirmation.props.visible, true)
	assert.equal(saves.length, 1, 'used values wait for confirmation')
	confirmation.props.onConfirm()
	await flush()
	assert.deepEqual(saves.at(-1), [attribute, props.values.filter(value => value !== selected)])
	finishSave()
	await flush()
	assert.ok(!props.values.includes(selected))
	app.unmount()
}

const css = readFileSync(`${base}sections.css`, 'utf8')
assert.match(css, /\.ipd-item-details-row\.ipd-fields, \.ipd-item-details-row\.ipd-facts\s*\{\s*grid-template-columns: repeat\(6, minmax\(0, 1fr\)\)/)
assert.match(css, /\.ipd-item-details-wide\.ipd-fields, \.ipd-item-details-wide\.ipd-facts\s*\{\s*grid-template-columns: minmax\(0, 1fr\)/)
assert.match(css, /@media \(max-width: 900px\)\s*\{\s*\.ipd-item-details-row[\s\S]*?repeat\(3, minmax\(0, 1fr\)\)/)
assert.match(css, /@media \(max-width: 640px\)\s*\{\s*\.ipd-item-details-row[\s\S]*?grid-template-columns: minmax\(0, 1fr\)/)
console.log('IPD details: layout, scoped LinkField suggestions, pending/saved duplicates, Enter saves/resets, invalid text rejection and usage confirmation passed')
