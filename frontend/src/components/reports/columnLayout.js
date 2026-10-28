export const MIN_COLUMN_WIDTH = 30
export const COLUMN_LAYOUT_PREFIX = "yrp-report-columns"

export function clampColumnWidth(width) {
	return Math.max(MIN_COLUMN_WIDTH, Math.round(Number(width) || 0))
}

/** One localStorage entry per report page and report title. */
export function columnLayoutStorageKey(path, title) {
	return `${COLUMN_LAYOUT_PREFIX}:${path}:${title}`
}

export function emptyColumnLayout() {
	return { widths: {}, order: {} }
}

export function readColumnLayout(storage, key) {
	try {
		const saved = JSON.parse(storage?.getItem(key) || "null")
		return { widths: saved?.widths || {}, order: saved?.order || {} }
	} catch {
		return emptyColumnLayout()
	}
}

export function writeColumnLayout(storage, key, layout) {
	const isEmpty = !Object.keys(layout.widths).length && !Object.keys(layout.order).length
	try {
		if (isEmpty) storage?.removeItem(key)
		else storage?.setItem(key, JSON.stringify(layout))
	} catch {
		// A blocked or full storage only loses the per-viewer layout.
	}
}

/**
 * Sorts `columns` by the saved label order. Pinned columns (frozen ones) keep their place; a column missing from
 * the saved order stays right after the column it followed originally.
 */
export function orderColumns(columns, order, { labelOf = column => column.label, isPinned = () => false } = {}) {
	if (!order?.length) return columns
	const rank = new Map(order.map((label, index) => [label, index]))
	const pinned = columns.filter(isPinned)
	let previous = -1
	const ranked = columns.filter(column => !isPinned(column)).map((column, index) => {
		const saved = rank.get(String(labelOf(column)))
		previous = saved ?? previous
		return { column, index, rank: saved ?? previous + 0.5 }
	})
	ranked.sort((left, right) => left.rank - right.rank || left.index - right.index)
	return [...pinned, ...ranked.map(entry => entry.column)]
}

/** Moves `label` so it lands before the column now at `targetIndex` (`labels.length` puts it last). */
export function moveColumnLabel(labels, label, targetIndex) {
	const from = labels.indexOf(label)
	if (from < 0) return labels
	const next = labels.filter(entry => entry !== label)
	const index = Math.min(Math.max(0, from < targetIndex ? targetIndex - 1 : targetIndex), next.length)
	next.splice(index, 0, label)
	return next
}

/** Header label of a column; repeated labels get a `#n` suffix so each keeps its own width. */
export function uniqueColumnLabels(labels) {
	const seen = new Map()
	return labels.map(label => {
		const count = seen.get(label) || 0
		seen.set(label, count + 1)
		return count ? `${label}#${count + 1}` : label
	})
}

/** Maps each header cell to its start column, honouring rowspan and colspan; rows marked data-export-ignore are skipped. */
export function headerGrid(rows) {
	const cells = []
	const carried = []
	let columnCount = 0
	for (const row of rows) {
		if (row.hasAttribute?.("data-export-ignore")) continue
		let column = 0
		const skipCarried = () => { while (carried[column] > 0) { carried[column] -= 1; column += 1 } }
		for (const cell of row.cells) {
			skipCarried()
			const span = Math.max(1, Number(cell.colSpan) || 1)
			const rowSpan = Math.max(1, Number(cell.rowSpan) || 1)
			cells.push({ cell, column, span })
			for (let offset = 0; offset < span; offset += 1) if (rowSpan > 1) carried[column + offset] = rowSpan - 1
			column += span
		}
		skipCarried()
		for (let index = column; index < carried.length; index += 1) if (carried[index] > 0) carried[index] -= 1
		columnCount = Math.max(columnCount, column)
	}
	return { cells, columnCount }
}
