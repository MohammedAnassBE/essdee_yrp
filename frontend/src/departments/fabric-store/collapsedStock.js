import { computed, ref, watch } from "vue"

import { getCollapsedStock } from "../../api/fabricStore.js"

export function collapsedPanelSummary(panels = []) {
	return panels.map((row) => `${row.panel} / ${row.colour} / ${row.size}: ${Number(row.quantity || 0).toLocaleString("en-IN", { maximumFractionDigits: 3 })}`).join(", ")
}

export function collapsedStockMessage({ panels = [], lot = "", location = "", allowNonBundle = false, doctypeLabel = "document", autoTick = true }) {
	if (!panels.length) return ""
	const stock = `Lot ${lot} cut panels at ${location} are collapsed stock (${collapsedPanelSummary(panels)}).`
	if (allowNonBundle) return `${stock} Allow Non Bundle is ticked, so this ${doctypeLabel} moves them by quantity.`
	const action = autoTick ? "Tick Allow Non Bundle" : `If this ${doctypeLabel} moves these panels, tick Allow Non Bundle`
	return `${stock} ${action}, or use a Cut Panel Movement with collapsed quantity. Moving them as exact bundles is blocked.`
}

/** Watch a draft's Lot and source, tick Allow Non Bundle for collapsed stock, and explain it. */
export function useCollapsedStockGuard({ enabled, lot, location, movement, allowNonBundle, setAllowNonBundle, doctypeLabel, autoTick = true }) {
	const panels = ref([])
	let request = 0
	watch(() => [enabled(), lot(), location(), movement()], async ([active, lotValue, locationValue, movementValue]) => {
		const current = ++request
		panels.value = []
		if (!active || !lotValue || !locationValue || movementValue) return
		try {
			const result = await getCollapsedStock(lotValue, locationValue)
			if (current !== request) return
			panels.value = result?.panels || []
			if (autoTick && panels.value.length && !Number(allowNonBundle() || 0)) setAllowNonBundle(1)
		} catch {
			if (current === request) panels.value = []
		}
	}, { immediate: true })
	const notice = computed(() => collapsedStockMessage({
		panels: panels.value,
		lot: lot(),
		location: location(),
		allowNonBundle: Boolean(Number(allowNonBundle() || 0)),
		doctypeLabel,
		autoTick,
	}))
	return { collapsedPanels: panels, collapsedStockNotice: notice }
}
