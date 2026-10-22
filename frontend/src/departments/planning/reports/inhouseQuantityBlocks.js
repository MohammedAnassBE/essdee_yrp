export const BLOCK_FIELDS = new Set(["number", "colour", "part", "supplier", "diff"])

const blockKey = (row) => (row.is_total_row ? `total:${row.part ?? ""}` : `row:${row.number}`)

/** Rowspan per row: block length on the first row of a colour/supplier block, 0 on the rows inside it. */
export function blockSpans(rows) {
	const spans = new Array(rows.length).fill(0)
	let start = 0
	rows.forEach((row, index) => {
		if (index > 0 && blockKey(row) !== blockKey(rows[start])) start = index
		spans[start] += 1
	})
	return spans
}

export function blockCellSpan(spans) {
	return (column, _row, index) => (BLOCK_FIELDS.has(column.fieldname) ? spans[index] : 1)
}
