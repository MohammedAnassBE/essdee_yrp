import { onBeforeUnmount, onMounted } from 'vue'
import { GRID_FOCUS_PART, gridFocusKey, gridRowKey } from '../ipdFocus.js'

export function useSectionFocus(editor, sectionKey, grids, part = '') {
	const unregister = []
	onMounted(() => {
		for (const field of Object.keys(grids)) {
			if (part && GRID_FOCUS_PART[field] !== part) continue
			unregister.push(editor.registerFocus(field, async (problem) => {
				const focusKey = gridFocusKey(field, editor.draft)
				const grid = grids[focusKey]?.()
				let rowKey = problem.row_key == null ? null : gridRowKey(editor.draft, field, problem.row_key)
				let column = field === 'ipd_processes' && problem.column === 'out_stage' ? 'in_stage' : problem.column
				if (field === 'marker_groups' && rowKey != null && column == null) {
					const groups = editor.draft.marker_groups || []
					const first = groups.findIndex((group) => group.includes(rowKey))
					const duplicate = groups.findIndex((group, index) => index > first && group.includes(rowKey))
					if (first >= 0) {
						column = rowKey
						rowKey = `group-${duplicate >= 0 ? duplicate : first}`
					}
				}
				return Boolean(await grid?.focusCell(rowKey, column ?? '', focusKey))
			}))
		}
	})
	onBeforeUnmount(() => unregister.forEach((remove) => remove()))
}
