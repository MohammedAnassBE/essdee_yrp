import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import test from 'node:test'
import { Vue, findNodes, loadComponent, mountComponent } from '../../scripts/helpers/vue_renderer.mjs'
import * as grid from '../src/components/common/entryGrid.js'
import * as purchaseLotViews from '../src/departments/purchase/lot/lotViews.js'
import * as targets from '../src/utils/linkTarget.js'

const nodes = (root, type) => findNodes(root, node => node.type === type)
const text = node => node.text + node.children.map(text).join('')
const control = () => null
function component(path, lotViews = purchaseLotViews) {
	return loadComponent(resolve(`frontend/src/${path}.vue`), {
		'vue-router': { useRouter: () => ({ push() {} }) },
		'../../utils/linkTarget.js': targets,
		'./entryGrid.js': grid,
		'./LinkField.vue': control,
		'./lotViews.js': lotViews,
		'../../purchase/lot/lotViews.js': lotViews,
		'primevue/button': control,
		'primevue/skeleton': control,
		'../../../components/documents/DocumentStatusBadge.vue': control,
	})
}
async function readable(allowed, run) {
	const previous = globalThis.window
	globalThis.window = {
		frappe: { boot: { user: { can_read: allowed } } },
		matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
		addEventListener() {}, removeEventListener() {},
	}
	try { await run() } finally { globalThis.window = previous }
}

// The lightweight renderer stores handlers; reproduce DOM ancestry and bubbling here.
function dispatch(target, handler, overrides = {}) {
	target.closest = selector => {
		for (let node = target; node; node = node.parent) if (node.type === selector) return node
		return null
	}
	const event = {
		target, button: 0, defaultPrevented: false, stopped: false,
		preventDefault() { this.defaultPrevented = true },
		stopPropagation() { this.stopped = true },
		...overrides,
	}
	for (let node = target; node && !event.stopped; node = node.parent) {
		event.currentTarget = node
		for (const fn of [node.props?.[handler]].flat().filter(Boolean)) fn(event)
	}
	return event
}
function mountGrid(readonly) {
	const changes = []
	const root = mountComponent(component('components/common/EntryGrid'), {
		rows: [{ key: 'r1', label: 'First' }, { key: 'r2', label: 'Second' }],
		columns: [{ key: 'item', label: 'Item', type: 'link', doctype: 'Item', fieldtype: 'Link', options: 'Item' }],
		modelValue: { r1: { item: 'ITEM/1' }, r2: { item: 'ITEM/2' } },
		readonly, 'onUpdate:modelValue': value => changes.push(value),
	})
	// Focus is a browser operation; selection and model changes remain real Vue state.
	nodes(root, 'table')[0].querySelector = () => null
	return { root, changes }
}

for (const readonly of [false, true]) {
	for (const key of ['Enter', 'Delete']) {
		for (const descendant of [false, true]) {
			test(`focused ${descendant ? 'anchor descendant' : 'anchor'} ${key} leaves ${readonly ? 'readonly' : 'editable'} grid untouched`, () => readable(['Item'], async () => {
				const { root, changes } = mountGrid(readonly)
				const anchor = nodes(root, 'a')[0]
				const target = descendant ? { type: 'span', props: {}, parent: anchor } : anchor
				const event = dispatch(target, 'onKeydown', { key })
				await Vue.nextTick()
				assert.equal(event.defaultPrevented, false)
				assert.deepEqual(nodes(root, 'td').map(node => node.props.tabindex), [0, -1])
				assert.deepEqual(changes, [])
				assert.equal(nodes(root, 'input').length, 0)
			}))
		}
	}
}

test('grid cells still handle Enter navigation and Delete clearing', () => readable(['Item'], async () => {
	const { root, changes } = mountGrid(false)
	assert.equal(dispatch(nodes(root, 'td')[0], 'onKeydown', { key: 'Enter' }).defaultPrevented, true)
	await Vue.nextTick()
	await Vue.nextTick()
	assert.deepEqual(nodes(root, 'td').map(node => node.props.tabindex), [-1, 0])
	assert.equal(dispatch(nodes(root, 'td')[1], 'onKeydown', { key: 'Delete' }).defaultPrevented, true)
	await Vue.nextTick()
	assert.equal(changes.length, 1)
	assert.equal(changes[0].r1.item, 'ITEM/1')
	assert.equal(changes[0].r2.item, null)
}))

for (const [department, lotViews] of [['purchase', purchaseLotViews], ['planning', purchaseLotViews]]) {
	for (const canRead of [false, true]) {
		test(`${department} rail Supplier ${canRead ? 'anchor stops' : 'fallback permits'} document card clicks`, () => readable(canRead ? ['Supplier'] : [], () => {
			const opened = []
			const root = mountComponent(component(`departments/${department}/lot/LotDocumentsRail`, lotViews), {
				documents: { purchase_orders: { count: 1, rows: [{ name: 'PO/1', supplier: 'SUP/1', supplier_name: 'Supplier Display' }] } },
				onOpen: value => opened.push(value),
			})
			const supplier = nodes(root, canRead ? 'a' : 'span').findLast(node => text(node) === 'Supplier Display')
			assert.ok(supplier)
			// Also cover clicks on content nested in the rendered anchor or fallback.
			for (const target of [supplier, { type: 'i', props: {}, parent: supplier }]) {
				opened.length = 0
				const event = dispatch(target, 'onClick')
				assert.equal(event.stopped, canRead)
				assert.deepEqual(opened, canRead ? [] : [{ doctype: 'Purchase Order', name: 'PO/1' }])
			}
		}))
	}
}
