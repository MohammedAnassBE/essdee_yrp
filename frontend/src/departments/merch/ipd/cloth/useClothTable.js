import { computed, inject, onBeforeUnmount, onMounted } from "vue"

import { IPD_EDITOR_KEY } from "../useIpdEditor.js"
import { gridRows, modelToRows, removeRow, rowsToModel } from "./clothGrids.js"

export function useClothSection(props) {
	const editor = inject(IPD_EDITOR_KEY)
	const readonly = computed(() => Boolean(props.readonly || editor.readonly))
	const cloth = computed(() => editor.context?.cloth || {})
	return { editor, readonly, cloth }
}

export function useClothTable(editor, field, fields, label = (row, index) => String(index + 1)) {
	const rows = computed(() => editor.draft[field] || [])
	const model = computed(() => rowsToModel(rows.value, fields))
	const keys = computed(() => gridRows(rows.value, label))
	const errors = computed(() => editor.gridErrors(field) || {})
	return {
		rows,
		model,
		keys,
		errors,
		update: (next) => editor.setValue(field, modelToRows(rows.value, next, fields)),
		add: (row) => editor.setValue(field, [...rows.value, row]),
		remove: (key) => editor.setValue(field, removeRow(rows.value, key)),
	}
}

export function useGridFocus(editor, sectionKey, targets) {
	const unregister = []
	onMounted(() => {
		for (const [field, target] of Object.entries(targets)) unregister.push(editor.registerFocus(field, (problem) => {
			const grid = target.grid?.value
			if (!grid) return false
			const rowKey = problem.row_key || target.firstRow?.()
			return grid.focusCell(rowKey ?? null, problem.column || target.firstColumn)
		}))
	})
	onBeforeUnmount(() => unregister.forEach((remove) => remove()))
}
