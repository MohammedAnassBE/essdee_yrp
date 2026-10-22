import { computed, nextTick, onBeforeUnmount, ref, toValue, watch } from "vue"

export const ROW_RENDER_STEP = 200

/**
 * Mounts a large result in steps: the first `step` rows, then `step` more whenever the
 * sentinel row scrolls near the viewport. `step: Infinity` mounts everything, for tables
 * whose export or copy reads the DOM.
 */
export function useIncrementalRows(rows, { step = ROW_RENDER_STEP, resetOn = rows } = {}) {
	const renderLimit = ref(step)
	const sentinel = ref(null)
	const renderedRows = computed(() => toValue(rows).slice(0, renderLimit.value))
	const unrenderedCount = computed(() => Math.max(0, toValue(rows).length - renderLimit.value))
	let observer = null

	function renderMoreRows() { renderLimit.value += step }

	watch(resetOn, () => { renderLimit.value = step })
	watch(sentinel, (element) => {
		observer?.disconnect()
		observer = null
		if (!element || typeof IntersectionObserver === "undefined") return
		observer = new IntersectionObserver(async (entries) => {
			if (!entries.some(entry => entry.isIntersecting)) return
			renderMoreRows()
			await nextTick()
			// Re-observing reports the sentinel again if it is still in view after the new rows.
			observer?.unobserve(element)
			observer?.observe(element)
		}, { rootMargin: "600px" })
		observer.observe(element)
	})
	onBeforeUnmount(() => observer?.disconnect())

	return { renderedRows, unrenderedCount, sentinel, renderMoreRows }
}
