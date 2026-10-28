import { computed, effectScope, inject, onBeforeUnmount, provide, reactive, toValue, watch } from "vue"

import { columnLayoutStorageKey, emptyColumnLayout, orderColumns, readColumnLayout, writeColumnLayout } from "../components/reports/columnLayout.js"
import { attachColumnLayout } from "../components/reports/columnLayoutController.js"

const LAYOUT = Symbol("reportColumnLayout")
const layouts = new Map()

function viewerStorage() {
	try {
		return globalThis.localStorage ?? null
	} catch {
		return null
	}
}

/** The one shared, persisted layout for a report title on the current page. */
export function columnLayoutFor(title) {
	const key = columnLayoutStorageKey(globalThis.location?.pathname || "", title)
	if (layouts.has(key)) return layouts.get(key)
	const storage = viewerStorage()
	const layout = reactive(readColumnLayout(storage, key))
	effectScope(true).run(() => watch(layout, () => writeColumnLayout(storage, key, layout), { deep: true }))
	layouts.set(key, layout)
	return layout
}

/** Attaches the resize and move handles to the tables under the `results` element ref while it is mounted. */
export function provideReportColumnLayout(title, results) {
	const layout = columnLayoutFor(toValue(title))
	let controller = null

	watch(layout, () => controller?.sync(), { deep: true, flush: "post" })
	watch(results, element => {
		controller?.detach()
		controller = element ? attachColumnLayout(element, layout) : null
	}, { flush: "post" })
	onBeforeUnmount(() => controller?.detach())

	const isCustomized = computed(() => Object.keys(layout.widths).length > 0 || Object.keys(layout.order).length > 0)
	function reset() {
		Object.assign(layout, emptyColumnLayout())
	}
	provide(LAYOUT, layout)
	return { layout, isCustomized, reset }
}

/**
 * Columns in the viewer's saved order for the table whose data-column-layout is `layoutKey`.
 * Bind `data-column-order` and `:data-column-layout="layoutKey"` on that table so its headers can be dragged.
 * Pass `report` (the ReportShell title) when the table is not inside the shell's own component tree.
 */
export function useOrderedColumns(layoutKey, columns, { report = "", ...options } = {}) {
	const layout = report ? columnLayoutFor(report) : inject(LAYOUT, null)
	return computed(() => {
		const source = toValue(columns) || []
		return layout ? orderColumns(source, layout.order[toValue(layoutKey)], options) : source
	})
}
