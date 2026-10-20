import { nextTick, onScopeDispose, ref, watch } from "vue"
import { moveDraftItem, reorderDraftItem } from "./orderedDraft.js"

const DIRECTIONS = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 }
const CONTROLS = "button, input, textarea, select, a, [contenteditable]"

function containsPoint(rect, x, y) {
	return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom
}

export function chipDropIndex(rects, x, y) {
	const anchors = rects.filter(rect => y >= rect.top && y <= rect.bottom)
	if (!anchors.length) {
		const below = rects.findIndex(rect => rect.top > y)
		return below < 0 ? rects.length : below
	}
	const top = Math.min(...anchors.map(rect => rect.top)), bottom = Math.max(...anchors.map(rect => rect.bottom))
	const row = rects.filter(rect => rect.top <= bottom && rect.bottom >= top)
	const before = row.find(rect => x < (rect.left + rect.right) / 2)
	return before ? rects.indexOf(before) : rects.indexOf(row.at(-1)) + 1
}

export function useChipReorder({ items, enabled, container, onReorder, announce }) {
	const dragging = ref(null)
	const dropIndex = ref(-1)
	let pointer = null
	const elements = () => Array.from(container.value?.querySelectorAll?.(":scope > [data-chip-value]") || [])

	function cancel() {
		const current = pointer
		pointer = null
		dragging.value = null
		dropIndex.value = -1
		current?.element.ownerDocument?.removeEventListener("keydown", escape, true)
		if (current?.element.hasPointerCapture?.(current.id)) current.element.releasePointerCapture(current.id)
	}
	function escape(event) {
		if (event.key !== "Escape" || !pointer) return
		event.preventDefault()
		event.stopPropagation()
		cancel()
	}
	function pointerdown(event, index) {
		if (!enabled() || pointer || event.button !== 0 || event.isPrimary === false) return
		if (event.target?.closest?.(CONTROLS)) return
		const element = event.currentTarget
		pointer = { id: event.pointerId, index, x: event.clientX, y: event.clientY, element, items: items() }
		element.setPointerCapture(event.pointerId)
		element.ownerDocument?.addEventListener("keydown", escape, true)
	}
	function position(event) {
		const { clientX: x, clientY: y } = event
		if (!containsPoint(container.value.getBoundingClientRect(), x, y)) return -1
		const excluded = Array.from(container.value.children || []).some(element =>
			element.dataset.chipValue === undefined && containsPoint(element.getBoundingClientRect(), x, y))
		if (excluded) return -1
		return chipDropIndex(elements().map(element => element.getBoundingClientRect()), x, y)
	}
	function pointermove(event) {
		if (!pointer || pointer.id !== event.pointerId) return
		if (!enabled() || pointer.items !== items()) { cancel(); return }
		if (Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y) < 4) return
		dragging.value = items()[pointer.index]
		dropIndex.value = position(event)
		event.preventDefault()
	}
	function focusMoved(before) {
		const doc = container.value?.ownerDocument
		const active = doc?.activeElement
		return Boolean(doc) && active !== before && active !== doc.body && !container.value.contains?.(active)
	}
	async function commit(ordered, value) {
		if (ordered === items()) return
		const before = container.value?.ownerDocument?.activeElement
		if (await onReorder(ordered) === false) return
		await nextTick()
		if (!focusMoved(before)) elements().find(element => element.dataset.chipValue === value)?.focus()
		announce(`Moved ${value} to position ${ordered.indexOf(value) + 1} of ${ordered.length}.`)
	}
	function pointerup(event) {
		if (!pointer || pointer.id !== event.pointerId) return
		const current = pointer
		const destination = dragging.value === null ? -1 : position(event)
		cancel()
		if (!enabled() || current.items !== items() || destination < 0) return
		return commit(reorderDraftItem(items(), current.index, destination), items()[current.index])
	}
	function keydown(event, index) {
		if (event.key === "Escape") { escape(event); return }
		if (!enabled() || !event.altKey || !DIRECTIONS[event.key] || event.target?.closest?.(CONTROLS)) return
		event.preventDefault()
		cancel()
		return commit(moveDraftItem(items(), index, DIRECTIONS[event.key]), items()[index])
	}
	function chipProps(value, index) {
		const active = enabled()
		return {
			role: "listitem", tabindex: active ? 0 : undefined,
			"data-chip-value": active ? value : undefined,
			"aria-label": active ? `${value}, position ${index + 1} of ${items().length}. Alt+Left or Alt+Right to move.` : undefined,
			class: {
				"is-reorderable": active, "is-dragging": dragging.value === value,
				"is-drop-before": dropIndex.value === index,
				"is-drop-after": dropIndex.value === items().length && index === items().length - 1,
			},
			onPointerdown: event => pointerdown(event, index), onPointermove: pointermove, onPointerup: pointerup,
			onPointercancel: cancel, onLostpointercapture: cancel, onKeydown: event => keydown(event, index),
		}
	}

	watch([items, enabled], cancel, { flush: "sync" })
	onScopeDispose(cancel)
	return { chipProps }
}
