import { computed, onBeforeUnmount, onMounted, ref, toValue, watch } from "vue"

import { callMethod, callRead } from "../../../api/frappe.js"
import { gridViewEntries, resolveGridColumns } from "./childGridColumns.js"
import { createGridViewStore } from "./gridViewStore.js"

export const gridViewStore = createGridViewStore({ read: callRead, write: callMethod })

/** Visible columns for a child table, following the user's Frappe GridView settings when the table has one. */
export function useGridColumns(columns, { parentDoctype, childDoctype } = {}) {
	const saved = ref(null)
	const error = ref("")
	const canConfigure = computed(() => Boolean(toValue(parentDoctype) && toValue(childDoctype)))
	const visibleColumns = computed(() => resolveGridColumns(toValue(columns) || [], saved.value))

	async function load() {
		saved.value = null
		if (!canConfigure.value) return
		try {
			saved.value = await gridViewStore.get(toValue(parentDoctype), toValue(childDoctype))
		} catch (reason) {
			error.value = reason.message || "Unable to load column settings."
		}
	}

	async function save(draft) {
		const entries = draft ? gridViewEntries(draft) : null
		await gridViewStore.save(toValue(parentDoctype), toValue(childDoctype), entries)
		saved.value = entries
	}

	watch(() => [toValue(parentDoctype), toValue(childDoctype)], load, { immediate: true })
	return { visibleColumns, canConfigure, error, save, reset: () => save(null) }
}

/** Live content width of an element, for percentage column layouts. */
export function useContainerWidth(element) {
	const width = ref(0)
	let observer = null
	onMounted(() => {
		const target = toValue(element)
		if (!target || typeof ResizeObserver === "undefined") return
		observer = new ResizeObserver(([entry]) => { width.value = Math.floor(entry.contentRect.width) })
		observer.observe(target)
	})
	onBeforeUnmount(() => observer?.disconnect())
	return width
}
