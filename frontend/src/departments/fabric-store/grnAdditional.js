const isChecked = (value) => [true, 1, "1"].includes(value)

/** Like production_api: Work Order receipts carry the flag; the source decides its rows, so only a new draft may toggle it. */
export function additionalGrnFieldState({ against, isReturn, isRework, isNew, canEditDraft }) {
	const visible = against === "YRP Work Order" && !isChecked(isReturn) && !isChecked(isRework)
	return { visible, editable: Boolean(visible && isNew && canEditDraft) }
}

export function additionalGrnSourceContext(sourceContext, checked) {
	return { ...(sourceContext || {}), additional_grn: checked ? 1 : 0 }
}
