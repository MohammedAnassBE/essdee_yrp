const state = new WeakMap()

/** scrollLeft that brings a cell (left/right relative to the unscrolled table) inside a view of viewWidth. */
export function getScrollLeftToReveal({ cellLeft, cellRight, viewWidth, scrollLeft }) {
	if (cellLeft < scrollLeft) return Math.max(0, cellLeft)
	if (cellRight > scrollLeft + viewWidth) return Math.min(cellLeft, cellRight - viewWidth)
	return scrollLeft
}

function parts(wrap) {
	return { table: wrap.querySelector(":scope > table"), bar: wrap.querySelector(":scope > [data-horizontal-scrollbar]") }
}

function measure(wrap) {
	const { table, bar } = parts(wrap)
	bar.firstElementChild.style.width = `${table.scrollWidth}px`
	bar.hidden = table.scrollWidth <= wrap.clientWidth + 1
	if (bar.hidden) bar.scrollLeft = 0
}

function revealFocused(wrap, event) {
	const { table, bar } = parts(wrap)
	const cell = event.target.closest?.("td, th")
	if (!cell || bar.hidden) return
	const tableLeft = table.getBoundingClientRect().left
	const box = cell.getBoundingClientRect()
	bar.scrollLeft = getScrollLeftToReveal({ cellLeft: box.left - tableLeft, cellRight: box.right - tableLeft, viewWidth: wrap.clientWidth, scrollLeft: bar.scrollLeft })
}

/**
 * v-synced-horizontal-scroll on a clipped (`overflow: clip`) table wrapper. Its child [data-horizontal-scrollbar]
 * scrolls sideways and slides the table, so the wrapper never becomes a scroll container and the thead can stick to
 * the page or dialog scroller. Without that child the directive does nothing.
 */
export const vSyncedHorizontalScroll = {
	mounted(wrap) {
		const { table, bar } = parts(wrap)
		if (!bar) return
		const onBarScroll = () => { table.style.translate = bar.scrollLeft ? `${-bar.scrollLeft}px 0` : "" }
		const onWheel = (event) => { if (event.deltaX) bar.scrollLeft += event.deltaX }
		const onFocus = (event) => revealFocused(wrap, event)
		const observer = new ResizeObserver(() => measure(wrap))
		observer.observe(wrap)
		observer.observe(table)
		bar.addEventListener("scroll", onBarScroll, { passive: true })
		wrap.addEventListener("wheel", onWheel, { passive: true })
		wrap.addEventListener("focusin", onFocus)
		state.set(wrap, { observer, onBarScroll, onWheel, onFocus })
	},
	beforeUnmount(wrap) {
		if (!state.has(wrap)) return
		const { observer, onBarScroll, onWheel, onFocus } = state.get(wrap)
		observer.disconnect()
		parts(wrap).bar.removeEventListener("scroll", onBarScroll)
		wrap.removeEventListener("wheel", onWheel)
		wrap.removeEventListener("focusin", onFocus)
		state.delete(wrap)
	},
}
