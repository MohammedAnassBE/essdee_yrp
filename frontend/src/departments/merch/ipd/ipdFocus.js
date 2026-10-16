import { problemTab } from './ipdTabs.js'

const ROW_VALUE_FIELDS = {
	packing_attribute_details: 'attribute_value',
	packing_size_details: 'attribute_value',
	stiching_item_details: 'stiching_attribute_value',
}

// Each field belongs to a particular rendered part, even when that part has no rows.
export const GRID_FOCUS_PART = Object.freeze({
	cloth_detail: 'cloths', cutting_items_json: 'consumption', cutting_cloths_json: 'mapping',
	panel_wise_consumption_matrix_json: 'consumption', panel_wise_cloth_mapping_json: 'mapping',
	stiching_item_details: 'items', stiching_item_detail: 'combination', marker_groups: 'bundles',
	ipd_processes: 'general', emblishment_details_json: 'embellishment', item_bom: 'bom',
	accessory_clothtype_json: 'accessories', cloth_accessory_json: 'accessories', stiching_accessory_json: 'stitching',
	packing_attribute_details: 'values', packing_size_details: 'values', packing_assortment_json: 'values',
})
export function gridFocusKey(field, draft = {}) {
	if (Number(draft.enable_panel_wise_consumption_matrix)) {
		if (field === 'cutting_items_json') return 'panel_wise_consumption_matrix_json'
		if (field === 'cutting_cloths_json') return 'panel_wise_cloth_mapping_json'
	}
	return field
}

export function problemFocusFallbacks(problem) {
	if (problem.field === 'packing_attribute_details') return [
		{ ...problem, field: 'packing_values', section: 'packing', row_key: null, column: null },
		{ ...problem, field: 'packing_attribute', row_key: null, column: null },
	]
	return []
}

export async function goToProblem(problem, frame, focusProblem) {
	for (const target of [problem, ...problemFocusFallbacks(problem)]) {
		await frame?.jumpTo(problemTab(target), { focus: false })
		if (await focusProblem(target)) return true
	}
	return GRID_FOCUS_PART[problem.field] ? false : frame?.focusFirstControl() || false
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
		for (const key of GRID_FOCUS_PART[problem.field] ? [problem.field] : [problem.field, problem.section]) {
			for (const handler of handlers.get(key) || []) if (await handler(problem)) return true
		}
		const element = problem.field && document.getElementById(`ipd-edit-${problem.field}`)
		element?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
		element?.focus({ preventScroll: true })
		return Boolean(element && document.activeElement === element)
	}
	return { registerFocus, focusProblem }
}
