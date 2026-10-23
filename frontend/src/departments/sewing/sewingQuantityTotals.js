/** Sum quantities, ignoring blanks and non-numbers, rounded to 3 decimals. */
export function sumQuantities(values) {
	const total = (values || []).reduce((sum, value) => sum + (Number.isFinite(Number(value)) ? Number(value || 0) : 0), 0)
	return Math.round(total * 1000) / 1000
}

function cellTotals(cells, quantities, contextColumns) {
	return {
		quantity: sumQuantities(cells.map((cell) => quantities[cell.order_detail])),
		context: Object.fromEntries(contextColumns.map((column) => [column.key, sumQuantities(cells.map((cell) => cell[column.key]))])),
	}
}

/** Per colour, per size and grand totals of a Sewing quantity matrix and its context columns. */
export function sewingMatrixTotals(colours, sizes, quantities = {}, contextColumns = []) {
	const entries = Object.entries(colours || {})
	const cellsOf = (colour) => sizes.map((size) => colour.values?.[size]).filter(Boolean)
	return {
		colours: Object.fromEntries(entries.map(([key, colour]) => [key, cellTotals(cellsOf(colour), quantities, contextColumns)])),
		sizes: Object.fromEntries(sizes.map((size) => [size, cellTotals(entries.map(([, colour]) => colour.values?.[size]).filter(Boolean), quantities, contextColumns)])),
		grand: cellTotals(entries.flatMap(([, colour]) => cellsOf(colour)), quantities, contextColumns),
	}
}

function uniqueReceivables(cells) {
	return [...new Map(cells.map((cell) => [`${cell.ref_doctype}:${cell.ref_docname}`, cell])).values()]
}

/** Received and pending totals of a Closed Work Order GRN group, one total row per UOM; received types sharing one receivable count its pending once. */
export function closedGrnTotals(rows, keys) {
	const uoms = [...new Set((rows || []).map((row) => row.default_uom || ""))]
	return uoms.map((uom) => {
		const uomRows = rows.filter((row) => (row.default_uom || "") === uom)
		const cells = (key) => uomRows.map((row) => row.values?.[key]).filter((cell) => cell?.ref_docname)
		const sizes = Object.fromEntries(keys.map((key) => [key, {
			qty: sumQuantities(cells(key).map((cell) => cell.qty)),
			pending: sumQuantities(uniqueReceivables(cells(key)).map((cell) => cell.pending_quantity)),
		}]))
		return {
			uom,
			sizes,
			qty: sumQuantities(Object.values(sizes).map((size) => size.qty)),
			pending: sumQuantities(Object.values(sizes).map((size) => size.pending)),
		}
	})
}

/** Received total of one Closed Work Order GRN row. */
export function closedGrnRowTotal(row, keys) {
	return sumQuantities(keys.map((key) => row.values?.[key]).filter((cell) => cell?.ref_docname).map((cell) => cell.qty))
}
