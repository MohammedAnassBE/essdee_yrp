import { getCurrentInstance, onBeforeUnmount, onMounted } from 'vue'
import { GRID_FOCUS_PART, gridFocusKey, gridRowKey } from '../ipdFocus.js'

export function useSectionFocus(editor, sectionKey, grids, part = '') {
	const unregister = []
	const instance = getCurrentInstance()
	onMounted(() => {
		for (const field of Object.keys(grids)) {
			if (part && GRID_FOCUS_PART[field] !== part) continue
			unregister.push(editor.registerFocus(field, async (problem) => {
				const focusKey = gridFocusKey(field, editor.draft)
				const grid = grids[focusKey]?.()
				const rowKey = problem.row_key == null ? null : gridRowKey(editor.draft, field, problem.row_key)
				const column = field === 'ipd_processes' && problem.column === 'out_stage' ? 'in_stage' : problem.column
				if (await grid?.focusCell(rowKey, column ?? '', focusKey)) return true
				// Keep the packing chips / attribute fallback when its quantity grid is disabled.
				if (field === 'packing_attribute_details' && !grid) return false
				const element = instance.vnode.el
				element?.setAttribute?.('tabindex', '-1')
				element?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
				element?.focus?.({ preventScroll: true })
				return Boolean(element && document.activeElement === element)
			}))
		}
	})
	onBeforeUnmount(() => unregister.forEach((remove) => remove()))
}
