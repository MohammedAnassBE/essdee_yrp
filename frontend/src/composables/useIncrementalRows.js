import { computed, inject, nextTick, onBeforeUnmount, provide, ref, toValue, watch } from "vue"

export const ROW_RENDER_STEP = 200
const FULL_RENDER_KEY = Symbol("reportFullRender")

/**
 * Mounts a large result in steps: the first `step` rows, then `step` more whenever the
 * sentinel row scrolls near the viewport. `step: Infinity` mounts everything. Inside a
 * `provideFullRender` owner (ReportShell), the owner can mount every row before it reads the DOM.
 */
export function useIncrementalRows(rows, { step = ROW_RENDER_STEP, resetOn = rows } = {}) {
	const renderLimit = ref(step)
	const sentinel = ref(null)
	const renderedRows = computed(() => toValue(rows).slice(0, renderLimit.value))
	const unrenderedCount = computed(() => Math.max(0, toValue(rows).length - renderLimit.value))
	let observer = null
	let resets = 0

	function renderMoreRows() { renderLimit.value += step }
	/** Mounts every row (for a copy or export capture); the returned function steps back unless `resetOn` already did. */
	function renderAllRows() {
		const previous = renderLimit.value
		const generation = resets
		renderLimit.value = Infinity
		return () => { if (generation === resets) renderLimit.value = previous }
	}

	const unregister = inject(FULL_RENDER_KEY, null)?.(renderAllRows)
	watch(resetOn, () => { resets += 1; renderLimit.value = step })
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
	onBeforeUnmount(() => {
		observer?.disconnect()
		unregister?.()
	})

	return { renderedRows, unrenderedCount, sentinel, renderMoreRows, renderAllRows }
}

/** Lets descendant `useIncrementalRows` tables register; the returned function mounts all their rows and resolves to a restore function. */
export function provideFullRender() {
	const renderers = new Set()
	provide(FULL_RENDER_KEY, (renderAll) => {
		renderers.add(renderAll)
		return () => renderers.delete(renderAll)
	})
	return async function renderAllRegisteredRows() {
		const restores = [...renderers].map(renderAll => renderAll())
		if (restores.length) await nextTick()
		return () => restores.forEach(restore => restore())
	}
}
