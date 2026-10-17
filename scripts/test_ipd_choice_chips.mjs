import assert from 'node:assert/strict'
import { Vue, createTestRenderer, findNodes, loadComponent } from './helpers/vue_renderer.mjs'

const Chips = loadComponent('frontend/src/departments/merch/ipd/sections/IpdChoiceChips.vue')
const root = { type: 'root', props: {}, children: [] }
const props = Vue.reactive({ label: 'Panels', choices: ['Front', 'Back', 'Sleeve'], selected: ['Back', 'Other'] })
const events = []
const chips = Vue.ref(null)
const app = createTestRenderer().createApp({ setup() {
	return () => Vue.h(Chips, { ...props, ref: chips, onToggle: (choice, on) => {
		events.push([choice, on])
		props.selected = on ? [...props.selected, choice] : props.selected.filter(value => value !== choice)
	} })
} })
app.mount(root)
const find = predicate => findNodes(root, predicate)[0]
const button = () => find(node => node.type === 'button')
const fieldset = () => find(node => node.type === 'fieldset')
const text = node => [node.text, ...node.children.map(text)].join('').trim()
const originalDocument = globalThis.document

try {
	assert.equal(text(button()), 'Select all')
	assert.equal(button().props.type, 'button', 'native button supports Tab, Enter and Space')
	assert.equal(button().props.tabindex, undefined, 'button stays in the native tab order')
	assert.equal(button().props['aria-label'], 'Select all Panels')
	assert.equal(button().props['aria-pressed'], false)
	assert.ok(findNodes(fieldset(), node => node === button()).length, 'toggle is inside the fieldset')
	assert.equal(find(node => node.type === 'legend').props.class, 'erp-field-label')
	button().props.onClick()
	assert.deepEqual(events, [['Front', true], ['Sleeve', true]], 'select only missing choices in choices order')
	await Vue.nextTick()
	assert.deepEqual(props.selected, ['Back', 'Other', 'Front', 'Sleeve'])
	assert.equal(text(button()), 'Clear all')
	assert.equal(button().props['aria-label'], 'Clear all Panels')
	assert.equal(button().props['aria-pressed'], true)
	events.length = 0
	button().props.onClick()
	assert.deepEqual(events, [['Front', false], ['Back', false], ['Sleeve', false]], 'clear in choices order, regardless of selected order')
	assert.deepEqual(props.selected, ['Other'], 'values outside choices are untouched')
	await Vue.nextTick()
	assert.equal(text(button()), 'Select all')

	props.label = ''
	await Vue.nextTick()
	assert.equal(button().props['aria-label'], 'Select all values')
	assert.equal(fieldset().children[0].type, 'legend', 'unlabelled toggle appears above the list')
	button().props.onClick()
	await Vue.nextTick()
	assert.equal(button().props['aria-label'], 'Clear all values')

	const click = button().props.onClick
	events.length = 0
	props.readonly = true
	await Vue.nextTick()
	assert.equal(button(), undefined, 'readonly hides the toggle')
	assert.equal(fieldset().props.disabled, true)
	click()
	assert.deepEqual(events, [], 'a retained handler cannot emit while readonly')
	props.readonly = false
	for (const choices of [[], ['Front']]) {
		props.choices = choices
		await Vue.nextTick()
		assert.equal(button(), undefined, 'fewer than two choices hides the toggle')
	}
	props.choices = []
	await Vue.nextTick()
	click()
	assert.deepEqual(events, [], 'no changes emit nothing')
	fieldset().querySelector = () => null
	assert.equal(chips.value.focus(), false, 'empty checklist cannot take checkbox focus')
	props.choices = ['Front', 'Back', 'Sleeve']
	props.selectAll = false
	await Vue.nextTick()
	assert.equal(button(), undefined, 'select-all=false hides the toggle')
	props.selectAll = true
	await Vue.nextTick()

	globalThis.document = { activeElement: null }
	const inputs = findNodes(root, node => node.type === 'input')
	inputs[0].props.disabled = true
	const selectors = []
	fieldset().querySelector = selector => {
		selectors.push(selector)
		assert.match(selector, /^input\b/, 'focus queries inputs, never the toggle button')
		return inputs.find(node => !selector.includes(':not(:disabled)') || !node.props.disabled)
	}
	let scrollOptions
	let focusOptions
	inputs[1].scrollIntoView = options => { scrollOptions = options }
	inputs[1].focus = options => { focusOptions = options; document.activeElement = inputs[1] }
	assert.equal(chips.value.focus(), true)
	assert.equal(document.activeElement, inputs[1], 'focus skips disabled checkboxes and the toggle')
	assert.ok(selectors.includes('input:not(:disabled)'))
	assert.deepEqual(scrollOptions, { block: 'nearest', inline: 'nearest' })
	assert.deepEqual(focusOptions, { preventScroll: true })
} finally {
	app.unmount()
	if (originalDocument === undefined) delete globalThis.document
	else globalThis.document = originalDocument
}
console.log('IPD choice chips: bulk toggle labels/events, visibility, readonly guard and checkbox focus passed')
