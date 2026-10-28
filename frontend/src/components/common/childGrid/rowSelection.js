import { computed, nextTick, ref, toValue } from "vue"

/** Selected keys ordered last row first, so removing one never shifts the index-based keys still to remove. */
export function removalOrder(keys, selected) {
	const chosen = new Set(selected)
	return keys.filter((key) => chosen.has(key)).reverse()
}

/** Desk-style row checkboxes: `selectableKeys` lists the rows that may be removed, in display order. */
export function useRowSelection(selectableKeys) {
	const picked = ref([])
	const keys = computed(() => toValue(selectableKeys) || [])
	const selected = computed(() => {
		const allowed = new Set(keys.value)
		return picked.value.filter((key) => allowed.has(key))
	})
	const isAllSelected = computed(() => keys.value.length > 0 && selected.value.length === keys.value.length)
	const isPartlySelected = computed(() => selected.value.length > 0 && !isAllSelected.value)

	function isSelected(key) {
		return selected.value.includes(key)
	}

	function toggle(key, on = !isSelected(key)) {
		const rest = selected.value.filter((candidate) => candidate !== key)
		picked.value = on && keys.value.includes(key) ? [...rest, key] : rest
	}

	function toggleAll(on = !isAllSelected.value) {
		picked.value = on ? [...keys.value] : []
	}

	/** Removes each selected row through `remove(key)`, stopping once `canRemove()` turns false. */
	async function removeSelected(remove, canRemove = () => true) {
		const order = removalOrder(keys.value, selected.value)
		picked.value = []
		for (const key of order) {
			if (!canRemove()) break
			await remove(key)
			await nextTick()
		}
	}

	return { selected, isAllSelected, isPartlySelected, isSelected, toggle, toggleAll, removeSelected }
}
