const INTERACTIVE = "a, button, input, textarea, select, label, [role='button'], [role='checkbox'], .p-checkbox"

/** True when a click on a table row should toggle it: not on a control inside the row, not ending a text selection. */
export function isRowToggleClick(event, view = globalThis) {
	if (event?.target?.closest?.(INTERACTIVE)) return false
	const selection = view.getSelection?.()
	return !(selection && !selection.isCollapsed && String(selection).trim())
}

/** True for Enter/Space pressed on the focused row itself. */
export function isRowToggleKey(event) {
	return event?.target === event?.currentTarget && (event.key === "Enter" || event.key === " ")
}
