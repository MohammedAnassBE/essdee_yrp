import { problemTab } from './ipdTabs.js'

const ROW_VALUE_FIELDS = {
	item_attributes: 'attribute',
	packing_attribute_details: 'attribute_value',
	packing_size_details: 'attribute_value',
	stiching_item_details: 'stiching_attribute_value',
}

// Each field belongs to a particular rendered part, even when that part has no rows.
export const GRID_FOCUS_PART = Object.freeze({
	item_attributes: '', set_item_detail: '', yarn_ratio_details: '', colour_yarn_recipes: '',
	fabric_routes: '', fabric_processes: '', fabric_value_mappings: '', compacting_reference_details: '',
	cloth_detail: 'cloths', cutting_items_json: 'consumption', cutting_cloths_json: 'mapping',
	panel_wise_consumption_matrix_json: 'consumption', panel_wise_cloth_mapping_json: 'mapping',
	stiching_item_details: 'items', stiching_item_detail: 'combination', marker_groups: 'bundles',
	ipd_processes: 'general', emblishment_details_json: 'embellishment', item_bom: 'bom',
	accessory_clothtype_json: 'accessories', cloth_accessory_json: 'accessories', stiching_accessory_json: 'stitching',
	packing_attribute_details: 'values', packing_size_details: 'values', packing_assortment_json: 'values',
})
const isGridField = (field) => Object.hasOwn(GRID_FOCUS_PART, field)

export function focusElement(element) {
	element?.setAttribute?.('tabindex', '-1')
	element?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
	element?.focus?.({ preventScroll: true })
	return Boolean(element && globalThis.document?.activeElement === element)
}

export function gridFocusKey(field, draft = {}) {
	if (Number(draft.enable_panel_wise_consumption_matrix)) {
		if (field === 'cutting_items_json') return 'panel_wise_consumption_matrix_json'
		if (field === 'cutting_cloths_json') return 'panel_wise_cloth_mapping_json'
	}
	return field
}

export function problemFocusFallbacks(problem) {
	if (problem.field === 'is_cloth_item') return [{ field: 'item', section: 'item' }]
	if (['packing_attribute_details', 'packing_size_details'].includes(problem.field) && problem.row_key == null) return [
		{ ...problem, field: 'packing_values', section: 'packing', row_key: null, column: null },
		{ ...problem, field: 'packing_attribute', row_key: null, column: null },
	]
	return []
}

export async function goToProblem(problem, frame, focusProblem) {
	problem = { ...problem, row_key: problem.row_key ?? problem.row }
	const navigation = frame?.problemNavigation?.(problem) || { target: problem, note: '' }
	frame?.reportProblem?.(navigation.note)
	if (!navigation.target) {
		await frame?.jumpTo('item_details_tab', { focus: false })
		frame?.focusProblemHeading?.(problem)
		return false
	}
	for (const target of [navigation.target, ...problemFocusFallbacks(navigation.target)]) {
		await frame?.jumpTo(problemTab(target), { focus: false })
		if (await focusProblem(target)) return true
	}
	frame?.focusProblemHeading?.(navigation.target)
	frame?.reportProblem?.([navigation.note, 'Cell not located. Review this section.'].filter(Boolean).join(' '))
	return false
}
export function gridRowKey(draft, field, rowKey) {
	const valueField = ROW_VALUE_FIELDS[field]
	if (!valueField) return rowKey
	const rows = draft[field] || []
	const position = /^new:(\d+)$/.exec(String(rowKey))
	const row = rows.find((candidate) => candidate.name === rowKey) || (position ? rows[Number(position[1])] : null)
	return row?.[valueField] ?? rowKey
}

export function createFocusRegistry() {
	const handlers = new Map()
	function registerFocus(key, handler) {
		const entries = handlers.get(key) || new Set()
		entries.add(handler)
		handlers.set(key, entries)
		return () => {
			entries.delete(handler)
			if (!entries.size) handlers.delete(key)
		}
	}
	async function focusProblem(problem) {
		problem = { ...problem, row_key: problem.row_key ?? problem.row }
		for (const handler of handlers.get(problem.field) || []) if (await handler(problem)) return true
		const element = problem.field && globalThis.document?.getElementById(`ipd-edit-${problem.field}`)
		const target = isGridField(problem.field) || problem.row_key != null || problem.column ? null : element
		return focusElement(target)
	}
	return { registerFocus, focusProblem }
}
