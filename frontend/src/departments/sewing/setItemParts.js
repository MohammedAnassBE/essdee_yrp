/** Distinct set-item parts (e.g. Top, Bottom) across a Sewing Plan's colour rows, in row order. */
export function sewingColourParts(colours = {}) {
	return [...new Set(Object.values(colours || {}).map(colour => colour?.part).filter(Boolean))]
}

/** Header for the set-item part column: the IPD set item attribute, else "Part"; empty when the plan has no parts. */
export function sewingPartLabel(details = {}, colours = {}) {
	if (!details?.is_set_item && !sewingColourParts(colours).length) return ""
	return details?.set_attr || "Part"
}
