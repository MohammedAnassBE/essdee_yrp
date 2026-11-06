export const GRN_QUANTITY = "GRN Quantity"

export function isLineWise(filters = {}) {
	return filters.fromType !== GRN_QUANTITY && filters.toType !== GRN_QUANTITY
}

export function pendingArgs(supplier, filters = {}) {
	return {
		supplier,
		from_type: filters.fromType || "",
		to_type: filters.toType || "",
		lots: [...(filters.lots || [])],
		items: [...(filters.items || [])],
		work_station: isLineWise(filters) ? filters.workStation || "" : "",
	}
}

export function pendingGroupLabel(group, lineWise) {
	if (!lineWise) return "All Work Stations"
	return group.work_station || "Not Specified"
}

export function pendingRowKey(group, row) {
	return [group.work_station, row.lot, row.item, row.work_order].join("\u0000")
}

/** Colours down, sizes across; every cell is a positive From minus To difference. */
export function gridColumns(row) {
	return [
		{ key: "colour", label: "Colour", wrap: true },
		...(row.has_part ? [{ key: "part", label: "Part" }] : []),
		...(row.sizes || []).map(size => ({ key: `size:${size}`, label: size, numeric: true })),
		{ key: "total", label: "Total", numeric: true },
	]
}

export function gridRows(row) {
	return (row.colours || []).map(colour => ({
		key: `${colour.colour}\u0000${colour.part || ""}`,
		colour: colour.colour,
		part: colour.part || "",
		total: colour.total,
		...Object.fromEntries((row.sizes || []).map(size => [`size:${size}`, colour.values?.[size] ?? null])),
	}))
}

export function gridTotals(row) {
	return { total: row.pending, ...Object.fromEntries((row.sizes || []).map(size => [`size:${size}`, row.size_totals?.[size] ?? 0])) }
}
