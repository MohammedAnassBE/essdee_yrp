/** Sum quantities, ignoring blanks and non-numbers, rounded to 3 decimals. */
export function sumQuantities(values) {
	const total = (values || []).reduce((sum, value) => sum + (Number.isFinite(Number(value)) ? Number(value || 0) : 0), 0)
	return Math.round(total * 1000) / 1000
}

function sizeTotals(sizes, valueOf) {
	const bySize = Object.fromEntries(sizes.map((size) => [size, sumQuantities(valueOf(size))]))
	return { sizes: bySize, total: sumQuantities(Object.values(bySize)) }
}

/** Totals across colours of one reference row (Balance, Delivered, ...) of a Finishing entry matrix. */
export function referenceTotals(rows, colours, sizes, key) {
	return sizeTotals(sizes, (size) => colours.map((colour) => rows[colour]?.values?.[size]?.[key]))
}

/** Totals across colours of the quantity being entered; unticked colours count as zero when `checkable`. */
export function inputTotals(entry, colours, sizes, checkable = false) {
	const included = colours.filter((colour) => !checkable || entry[colour]?.checked)
	return sizeTotals(sizes, (size) => included.map((colour) => entry[colour]?.sizes?.[size]))
}

/** Rework, Rejection and Reworked totals across the sizes of one rework group. */
export function reworkTotals(items) {
	const total = (field) => sumQuantities((items || []).map((item) => item[field]))
	return { rework_qty: total("rework_qty"), rejected: total("rejected"), rework: total("rework") }
}

/** Balance and transfer totals of one old lot bucket (`field`, `balanceField`) across colours. */
export function lotTransferTotals(row, transfer, field, balanceField) {
	const colours = Object.keys(row.old_lot_inward?.data || {})
	const sizes = row.primary_values || []
	return {
		balance: sizeTotals(sizes, (size) => colours.map((colour) => row.old_lot_inward.data[colour].values?.[size]?.[balanceField])),
		transfer: sizeTotals(sizes, (size) => colours.map((colour) => transfer?.[colour]?.sizes?.[size]?.[field])),
	}
}
