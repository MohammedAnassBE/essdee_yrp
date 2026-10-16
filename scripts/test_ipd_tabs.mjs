#!/usr/bin/env node
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { IPD_TABS, preloadSectionKeys, problemTab } from '../frontend/src/departments/merch/ipd/ipdTabs.js'
import { createFocusRegistry, goToProblem, problemFocusFallbacks } from '../frontend/src/departments/merch/ipd/ipdFocus.js'
import { useSectionFocus } from '../frontend/src/departments/merch/ipd/sections/sectionFocus.js'
import { markerGrid } from '../frontend/src/departments/merch/ipd/sections/garmentGrids.js'
import { useGridFocus } from '../frontend/src/departments/merch/ipd/cloth/useClothTable.js'
import * as entryGrid from '../frontend/src/components/common/entryGrid.js'
import { Vue, createTestRenderer, findNodes, loadComponent } from './helpers/vue_renderer.mjs'

const root = new URL('../frontend/src/departments/merch/ipd/', import.meta.url)
const source = (file) => readFileSync(new URL(file, root), 'utf8')

// Sections in every tab keep their content height inside the scrolling panel.
const css = source('ipd.css')
for (const [, selectors, declarations] of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
	if (selectors.split(',').some((selector) => selector.trim() === '.ipd-tab-section')) {
		assert.doesNotMatch(declarations, /min-height:\s*0\b/, 'sections must never opt out of their content minimum')
	}
}
assert.match(css, /\.ipd-tab-panel\s*\{[^}]*grid-auto-rows:\s*max-content/)
assert.match(css, /\.ipd-tab-section\s*\{[^}]*min-height:\s*auto/)
assert.match(css, /\.ipd-tab-panel\s*\{[^}]*overflow-y:\s*auto/)

const garmentKeys = ['item', 'attributes', 'accessories', 'processes', 'packing', 'set_item', 'stitching', 'cutting', 'settings']
assert.deepEqual(preloadSectionKeys(IPD_TABS, {}).sort(), garmentKeys.sort(), 'warm hidden Set Item and saved-document chunks, even on a new garment')
const clothKeys = preloadSectionKeys(IPD_TABS, { is_cloth_item: 1 })
assert.deepEqual(clothKeys.sort(), ['item', 'attributes', 'processes', 'fabric_processes', 'yarn_ratio', 'fabric_routes', 'compacting'].sort())
assert.deepEqual(preloadSectionKeys([{ sections: [{ parts: [{ component: 'custom' }] }] }], {}), ['custom'], 'preloading follows the supplied registry')

// Exercise the real async component cache with deferred chunk imports.
const registrySource = source('ipdSectionRegistry.js')
const registryBody = registrySource.replace(/^import .*\n/gm, '').replace(/const loaders = import\.meta\.glob\([^\n]+\)/, '').replaceAll('export ', '')
const { defineAsyncComponent, markRaw } = Vue
const pending = new Map()
const calls = []
const loaders = Object.fromEntries(garmentKeys.map((key) => {
	const file = registrySource.match(new RegExp(`\\b${key}: "([^"]+)"`))[1]
	return [file, () => {
		calls.push(key)
		return new Promise((resolve) => pending.set(key, resolve))
	}]
}))
const registry = new Function('defineAsyncComponent', 'markRaw', 'IpdSectionPlaceholder', 'loaders', `${registryBody}\nreturn { sectionComponent, preloadSectionComponents }`)(defineAsyncComponent, markRaw, {}, loaders)
const warming = registry.preloadSectionComponents([...garmentKeys, 'packing'])
await Promise.resolve()
await Promise.resolve()
assert.deepEqual(calls.sort(), garmentKeys.sort(), 'all chunks start in parallel before any completes')
const warmingAgain = registry.preloadSectionComponents(garmentKeys)
for (const [key, resolve] of pending) resolve({ default: { name: key, render: () => null } })
assert.ok((await warming).every((result) => result.status === 'fulfilled'))
await warmingAgain
await registry.sectionComponent('packing').__asyncLoader()
assert.equal(calls.length, garmentKeys.length, 'preload and first tab visit reuse each import')
const sectionsSource = source('IpdSections.vue')
assert.match(sectionsSource, /watch\(\(\) => preloadSectionKeys\(props.tabs, props.doc\)[^\n]+immediate: true/)
assert.match(sectionsSource, /await Promise.all\(parts.map[^\n]+__asyncLoader/)
assert.match(sectionsSource, /await nextTick\(\)\s+await nextTick\(\)/)

const { parse } = createRequire(new URL('../frontend/package.json', import.meta.url))('@vue/compiler-sfc')
const processTemplate = parse(source('sections/IpdProcessesSection.vue')).descriptor.template.content
const general = processTemplate.split(`<template v-if="part === 'general'">`)[1].split('</template>')[0]
const embellishment = processTemplate.split(`<template v-if="part === 'embellishment'">`)[1].split('</template>')[0]
assert.doesNotMatch(general, /Embellishment processes use/)
assert.match(embellishment, /Embellishment processes use the stitching in stage when saved/)

const previousDocument = globalThis.document
globalThis.document = { activeElement: null, getElementById: () => null }
const packingProblem = { section: 'packing', field: 'packing_attribute_details', row_key: null, message: 'Packing Attribute is required' }
assert.deepEqual(problemFocusFallbacks(packingProblem).map(({ field }) => field), ['packing_values', 'packing_attribute'])
assert.deepEqual(problemFocusFallbacks({ ...packingProblem, field: 'packing_size_details' }).map(({ field }) => field), ['packing_values', 'packing_attribute'])
for (const field of ['packing_attribute_details', 'packing_size_details']) {
	assert.deepEqual(problemFocusFallbacks({ ...packingProblem, field, row_key: 'row-1' }), [], 'row problems must stay with their grid')
}
assert.deepEqual(problemFocusFallbacks({ field: 'item' }), [])
assert.equal(problemTab(packingProblem), 'packing_tab')
assert.equal(problemTab({ section: 'packing', field: 'packing_attribute' }), 'advance_settings_tab')
assert.equal(problemTab({ section: 'review', field: 'colour_yarn_recipes' }), 'fabric_processes_tab')
for (const hasAttribute of [false, true]) {
	const registry = createFocusRegistry()
	const events = []
	registry.registerFocus('packing_attribute_details', () => false) // grid absent in auto calculate mode
	registry.registerFocus('packing_values', () => { events.push('chips'); return hasAttribute })
	registry.registerFocus('packing_attribute', () => { events.push('attribute'); return true })
	const frame = {
		async jumpTo(tab) { events.push(`loading:${tab}`); await Promise.resolve(); events.push(`ready:${tab}`) },
		focusFirstControl() { throw new Error('a related packing control must take focus') },
	}
	assert.equal(await goToProblem(packingProblem, frame, registry.focusProblem), true)
	assert.deepEqual(events, hasAttribute
		? ['loading:packing_tab', 'ready:packing_tab', 'loading:packing_tab', 'ready:packing_tab', 'chips']
		: ['loading:packing_tab', 'ready:packing_tab', 'loading:packing_tab', 'ready:packing_tab', 'chips', 'loading:advance_settings_tab', 'ready:advance_settings_tab', 'attribute'])
}

// Mount the actual readonly EntryGrid and drive both real per-field focus hooks.
// Each grid field is checked against its section registration as well as focusing
// the second row/column; a panel or the grid's default first cell cannot pass.
const fieldsBySection = {
	'sections/IpdPackingSection.vue': ['packing_attribute_details', 'packing_size_details', 'packing_assortment_json'],
	'sections/IpdSetItemSection.vue': ['set_item_detail'],
	'sections/IpdStitchingSection.vue': ['stiching_item_details', 'stiching_item_detail', 'marker_groups'],
	'sections/IpdProcessesSection.vue': ['ipd_processes', 'emblishment_details_json'],
	'sections/IpdCuttingSection.vue': ['cloth_detail', 'cutting_items_json', 'cutting_cloths_json', 'panel_wise_consumption_matrix_json', 'panel_wise_cloth_mapping_json'],
	'sections/IpdAccessoriesSection.vue': ['item_bom', 'accessory_clothtype_json', 'cloth_accessory_json', 'stiching_accessory_json'],
	'cloth/IpdYarnRatioSection.vue': ['yarn_ratio_details', 'colour_yarn_recipes'],
	'cloth/IpdFabricProcessesSection.vue': ['fabric_processes', 'fabric_value_mappings'],
	'cloth/IpdFabricRoutesSection.vue': ['fabric_routes'],
	'cloth/IpdCompactingSection.vue': ['compacting_reference_details'],
}
const EntryGrid = loadComponent(new URL('../frontend/src/components/common/EntryGrid.vue', import.meta.url).pathname, {
	'primevue/button': { render: () => null }, './LinkField.vue': { render: () => null }, './entryGrid.js': entryGrid,
})
const previousWindow = globalThis.window
globalThis.window = { removeEventListener() {} }
try {
	for (const [file, fields] of Object.entries(fieldsBySection)) {
		const hookName = file.startsWith('cloth/') ? 'useGridFocus' : 'useSectionFocus'
		const registration = source(file).split(`${hookName}(editor, props.sectionKey, {`)[1].split('\n})')[0]
		for (const field of fields) assert.match(registration, new RegExp(`\\b${field}:`), `${file} registers ${field} in readonly too`)
		const registry = createFocusRegistry()
		const grid = Vue.ref(null)
		const api = { readonly: true, draft: {}, registerFocus: registry.registerFocus }
		const container = { type: 'root', children: [] }
		const app = createTestRenderer().createApp({
			setup() {
				if (hookName === 'useGridFocus') useGridFocus(api, '', Object.fromEntries(fields.map((field) => [field, { grid }])))
				else useSectionFocus(api, '', Object.fromEntries(fields.map((field) => [field, () => grid.value])))
				return () => Vue.h(EntryGrid, { ref: grid, readonly: true, rows: [{ key: 'row-1' }, { key: 'row-2' }], columns: [{ key: 'first' }, { key: 'target' }], modelValue: {} })
			},
		})
		app.mount(container)
		const table = findNodes(container, (node) => node.type === 'table')[0]
		table.querySelector = (selector) => {
			const [, row, col] = selector.match(/data-row="(\d+)"\]\[data-col="(\d+)"/)
			return findNodes(table, (node) => node.type === 'td' && node.props['data-row'] === Number(row) && node.props['data-col'] === Number(col))[0]
		}
		for (const cell of findNodes(table, (node) => node.type === 'td')) {
			cell.focus = () => { document.activeElement = cell }
			cell.scrollIntoView = () => {}
		}
		for (const field of fields) {
			document.activeElement = null
			let ready = false
			const frame = { async jumpTo() { await Promise.resolve(); ready = true } }
			await goToProblem({ field, row_key: 'row-2', column: 'target' }, frame, (problem) => {
				assert.equal(ready, true, 'focus awaits the tab switch and chunk load')
				return registry.focusProblem(problem)
			})
			await Vue.nextTick()
			assert.equal(document.activeElement?.type, 'td', field)
			assert.equal(document.activeElement.props['data-row'], 1, field)
			assert.equal(document.activeElement.props['data-col'], 1, field)
		}
		app.unmount()
	}
	// Server bundle problems identify a panel; the grid identifies a group and panel.
	// Both editor and record modes must focus the duplicate checkbox, past row/col 0.
	for (const readonly of [false, true]) {
		const registry = createFocusRegistry()
		const grid = Vue.ref(null)
		const draft = { marker_groups: [['Back'], ['Sleeve', 'Front'], ['Back', 'Front']] }
		const markers = markerGrid(draft.marker_groups, ['Back', 'Sleeve', 'Front'])
		const container = { type: 'root', children: [] }
		const app = createTestRenderer().createApp({
			setup() {
				useSectionFocus({ readonly, draft, registerFocus: registry.registerFocus }, 'stitching', { marker_groups: () => grid.value }, 'bundles')
				return () => Vue.h(EntryGrid, { ref: grid, readonly, rows: markers.rows, columns: markers.columns, modelValue: markers.model })
			},
		})
		app.mount(container)
		const table = findNodes(container, node => node.props?.role === 'grid')[0]
		table.querySelector = selector => {
			const [, row, col] = selector.match(/data-row="(\d+)"\]\[data-col="(\d+)"/)
			return findNodes(table, node => node.type === 'td' && node.props['data-row'] === Number(row) && node.props['data-col'] === Number(col))[0]
		}
		for (const cell of findNodes(table, node => node.type === 'td')) {
			cell.focus = () => { document.activeElement = cell }
			cell.scrollIntoView = () => {}
		}
		for (const [row_key, column, expectedRow] of [['Front', null, 2], ['group-1', 'Front', 1]]) {
			document.activeElement = null
			const visits = []
			assert.equal(await goToProblem({ section: 'stitching', field: 'marker_groups', row_key, column }, {
				async jumpTo(tab) { visits.push(tab); await Promise.resolve() },
			}, registry.focusProblem), true)
			await Vue.nextTick()
			assert.deepEqual(visits, ['stiching_tab'])
			assert.equal(document.activeElement?.props.role, 'gridcell', `bundle checkbox focused in ${readonly ? 'record' : 'editor'} mode`)
			assert.equal(document.activeElement.props['data-row'], expectedRow)
			assert.equal(document.activeElement.props['data-col'], 2)
		}
		app.unmount()
	}
} finally {
	globalThis.document = previousDocument
	globalThis.window = previousWindow
}
for (const file of ['IpdPage.vue', 'IpdEditor.vue']) assert.match(source(file), /return goToProblem\(problem, frame.value, focusProblem\)/)
assert.match(source('IpdPage.vue'), /registerFocus, fieldSchema:/)
console.log('ipd tab layout, preloading, packing fallback and readonly cell focus tests passed')
