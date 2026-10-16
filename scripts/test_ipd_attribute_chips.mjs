import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { Vue, createTestRenderer, findNodes, loadComponent } from './helpers/vue_renderer.mjs'
import * as helpers from '../frontend/src/departments/merch/ipd/ipdEditor.js'
import * as autocompleteKeys from '../frontend/src/components/common/autocompleteKeys.js'

const filename = 'frontend/src/departments/merch/ipd/sections/IpdAttributeChips.vue'
const source = readFileSync(filename, 'utf8')
assert.match(source, /import LinkField from "[^"]*components\/common\/LinkField\.vue"/)
assert.match(source, /:search-handler="searchValues"/)
assert.match(source, /searchItemAttributeValues\(props\.attribute, query\)/)
assert.match(source, /@paste\.capture="onPaste"/)
assert.doesNotMatch(source, /<datalist\b|<input\b|suggestTimer|function suggest\(/)

// Compile both real components. Substitute only the PrimeVue control, API, and dialog.
const key = Symbol('chip-editor')
const searches = []
const catalogue = {
	Colour: [{ name: 'colour-black', label: 'BLACK' }, { name: 'colour-bottle', label: 'Bottle Green' }, { name: 'colour-comma', label: 'Blue, Green' }, { name: 'colour-navy', label: 'Navy' }, { name: 'colour-red', label: 'Red' }],
	Part: [{ name: 'part-bottom', label: 'Bottom' }],
}
let focused = 0
const AutoComplete = {
	inheritAttrs: false,
	props: ['modelValue', 'suggestions', 'disabled', 'ariaLabel', 'placeholder'],
	data: () => ({ searching: false, overlayVisible: true, focusedOptionIndex: -1 }),
	methods: {
		onKeyDown() {},
		findFirstOptionIndex() { return this.suggestions.length ? 0 : -1 },
		hide() { this.overlayVisible = false },
		onEnterKey() {
			const value = this.suggestions[this.focusedOptionIndex]
			if (value) this.$attrs.onItemSelect({ value })
		},
	},
	render() {
		return Vue.h('autocomplete', { ...this.$attrs, options: this.suggestions, modelValue: this.modelValue }, [
			Vue.h('input', { disabled: this.disabled, 'aria-label': this.ariaLabel, placeholder: this.placeholder }),
		])
	},
}
const Chips = loadComponent(filename, {
	'primevue/button': { render() { return Vue.h('button', this.$attrs) } },
	'primevue/autocomplete': AutoComplete,
	'./autocompleteKeys.js': autocompleteKeys,
	'../../api/frappe.js': { searchLink: () => { throw new Error('Attribute cards must use their own search handler') } },
	'../../router/webDocumentRoutes.js': { webDocumentPath: () => '' },
	'../../../../api/purchase.js': { async searchItemAttributeValues(attribute, query) {
		searches.push([attribute, query])
		return (catalogue[attribute] || []).filter(row => row.label.toLowerCase().includes(query.toLowerCase()))
	} },
	'../../../../components/documents/DocumentConfirmationDialog.vue': {
		render() { return Vue.h('confirmation', this.$attrs) },
	},
	'../ipdEditor.js': helpers,
	'../useIpdEditor.js': { IPD_EDITOR_KEY: key },
})
const root = { type: 'root', props: {}, children: [] }
const values = Vue.ref(['Black'])
const saves = []
const usages = []
let finishSave
let used = false
const editor = {
	async saveAttributeValues(attribute, next) {
		saves.push([attribute, next])
		await new Promise(resolve => { finishSave = resolve })
		const unknown = next.filter(value => !catalogue[attribute].some(row => row.label.toLowerCase() === value.toLowerCase()))
		if (unknown.length) throw new Error(`${unknown.join(', ')} is not a ${attribute} value. Pick values from the ${attribute} list.`)
		values.value = next
	},
	async valueUsage(attribute, requested) {
		usages.push([attribute, requested])
		return { [requested[0]]: used ? [{ section: 'packing', label: 'Packing rows', count: 1 }] : [] }
	},
}
const app = createTestRenderer().createApp({ setup() {
	Vue.provide(key, editor)
	return () => Vue.h(Chips, { attribute: 'Colour', values: values.value, editable: true })
} })
app.mount(root)
const find = predicate => findNodes(root, predicate)[0]
const auto = () => find(node => node.type === 'autocomplete')
const input = () => find(node => node.type === 'input')
const wrapper = () => find(node => node.props.onPasteCapture)
const field = () => find(node => node.props.onKeydownCapture)
const text = () => findNodes(root, () => true).map(node => node.text).join(' ')
const settle = async () => { for (let index = 0; index < 5; index++) await Vue.nextTick() }
input().focus = () => { focused += 1 }
auto().querySelector = () => input()
async function search(query) {
	const target = input()
	target.value = query
	auto().props['onUpdate:modelValue'](query)
	await auto().props.onComplete({ query })
	await settle()
}
async function finish() { finishSave(); await settle() }
function paste(value, current = '') {
	const event = { target: { tagName: 'INPUT', value: current }, clipboardData: { getData: () => value }, preventDefault() { this.prevented = true } }
	wrapper().props.onPasteCapture(event)
	return event
}
function backspace(value = '') {
	const event = { key: 'Backspace', target: { tagName: 'INPUT', value }, preventDefault() { this.prevented = true } }
	wrapper().props.onKeydown(event)
	return event
}
try {
	assert.equal(input().props['aria-label'], 'Add Colour values')
	assert.ok(input().props.placeholder.startsWith('+ add'))
	await search('b')
	assert.deepEqual(searches.at(-1), ['Colour', 'b'])
	assert.deepEqual(auto().props.options, catalogue.Colour.slice(1, 3).map(row => ({ name: row.label, label: row.label })), 'known labels are excluded without regard to case')
	await search('Bo')
	assert.deepEqual(auto().props.options, [{ name: 'Bottle Green', label: 'Bottle Green' }], 'Colour search never offers Part Bottom')
	await auto().props.onBeforeShow()
	field().props.onKeydownCapture({ key: 'Enter', target: input(), preventDefault() {}, stopPropagation() {} })
	await settle()
	assert.deepEqual(saves.at(-1), ['Colour', ['Black', 'Bottle Green']], 'save the selected label rather than its document name')
	assert.match(text(), /Bottle Green Saving/)
	await finish()
	assert.equal(auto().props.modelValue, null, 'selection resets the LinkField even though its model starts empty')
	assert.deepEqual(values.value, ['Black', 'Bottle Green'])
	assert.ok(focused > 0, 'focus returns to the field after saving')

	for (const trigger of ['Enter', 'blur']) {
		await search('Unknown Colour')
		if (trigger === 'Enter') field().props.onKeydownCapture({ key: 'Enter', target: input(), preventDefault() {}, stopPropagation() {} })
		else auto().props.onBlur()
		await settle()
		assert.match(text(), /Pick one from the list/)
		assert.equal(saves.length, 1, 'free text never saves on Enter or blur')
	}
	assert.equal(paste('Navy\nUnknown One\tUnknown Two').prevented, true)
	await settle()
	assert.equal(saves.length, 2, 'multi-value paste sends exactly one atomic save')
	assert.deepEqual(saves.at(-1)[1], ['Black', 'Bottle Green', 'Navy', 'Unknown One', 'Unknown Two'])
	assert.doesNotMatch(text(), /\d+ added/, 'paste reports additions only after a successful save')
	await finish()
	assert.match(text(), /Unknown One, Unknown Two is not a Colour value/)
	assert.deepEqual(values.value, ['Black', 'Bottle Green'], 'failed list save leaves chips unchanged')
	assert.doesNotMatch(text(), /\d+ added|Saving/)
	assert.equal(paste('Bottle Green\rblack\tBLACK').prevented, true)
	await settle()
	assert.equal(saves.length, 2, 'all-duplicate paste does not save')
	assert.match(text(), /3 already present/)
	assert.doesNotMatch(text(), /Unknown One|Unknown Two/, 'duplicate paste clears the previous card error')
	assert.equal(paste('Bottle Green').prevented, undefined, 'single-value paste stays with LinkField validation')

	// Select a catalogue label containing a comma without treating it as a list.
	await search('Blue, Green')
	auto().props.onItemSelect({ value: auto().props.options[0] })
	await settle()
	assert.deepEqual(saves.at(-1)[1], ['Black', 'Bottle Green', 'Blue, Green'])
	await finish()
	assert.equal(backspace('typed').prevented, undefined)
	assert.equal(saves.length, 3)
	assert.equal(backspace().prevented, true)
	await settle()
	assert.ok(find(node => String(node.props.class).includes('is-selected')))
	assert.equal(usages.length, 0, 'first Backspace selects the last chip without removing it')
	used = true
	backspace()
	await settle()
	assert.equal(find(node => node.type === 'confirmation').props.visible, true)
	assert.match(find(node => node.type === 'confirmation').props.message, /Packing rows/)
	assert.equal(saves.length, 3, 'used values wait for removal confirmation')
	find(node => node.type === 'confirmation').props.onConfirm()
	await settle()
	assert.deepEqual(saves.at(-1), ['Colour', ['Black', 'Bottle Green']])
	await finish()
	assert.equal(find(node => node.type === 'confirmation').props.visible, false)
	assert.deepEqual(values.value, ['Black', 'Bottle Green'], 'confirmed Backspace removal persists')
	assert.deepEqual(usages.at(-1), ['Colour', ['Blue, Green']])
	used = false
	find(node => node.type === 'button' && node.props['aria-label'] === 'Remove Bottle Green').props.onClick()
	await settle()
	await finish()
	assert.deepEqual(values.value, ['Black'], 'unused chip removal still saves directly')
	assert.deepEqual(usages.at(-1), ['Colour', ['Bottle Green']], 'x removal checks usage too')
	assert.equal(paste('Navy,\nRed\tblack').prevented, true)
	await settle()
	assert.equal(saves.length, 6, 'valid list paste uses one save for all new values')
	assert.deepEqual(saves.at(-1), ['Colour', ['Black', 'Navy', 'Red']])
	assert.doesNotMatch(text(), /\d+ added/, 'no success status appears while saving')
	await finish()
	assert.deepEqual(values.value, ['Black', 'Navy', 'Red'], 'valid paste adds values together and excludes duplicates')
	assert.match(text(), /2 added · 1 already present/)
} finally {
	app.unmount()
}
console.log('IPD chips: real LinkField search, selection, validation, reset/focus, atomic paste errors and confirmed removal passed')
