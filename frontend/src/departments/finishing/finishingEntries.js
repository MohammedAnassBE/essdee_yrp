/** Entry state and quantity rules for the Finishing Plan create dialogs (Frappe 15 behaviour). */

const number = (value) => Number(value) || 0
const round3 = (value) => Math.round(number(value) * 1000) / 1000

function rowsOf(payload) {
	return payload?.data?.data || {}
}

export function initialEntry(payload) {
	const sizes = payload?.primary_values || []
	return Object.fromEntries(Object.entries(rowsOf(payload)).map(([colour, row]) => [
		colour,
		{ checked: row.check_value ?? true, sizes: Object.fromEntries(sizes.map((size) => [size, 0])) },
	]))
}

export function fillEntry(payload, entry, field) {
	for (const [colour, row] of Object.entries(rowsOf(payload))) {
		if (!entry[colour]) continue
		for (const size of Object.keys(entry[colour].sizes)) entry[colour].sizes[size] = number(row.values?.[size]?.[field])
	}
	return entry
}

export function entryQuantities(entry) {
	return Object.fromEntries(Object.entries(entry).map(([colour, row]) => [
		colour,
		{ checked: Boolean(row.checked), sizes: Object.fromEntries(Object.entries(row.sizes).map(([size, value]) => [size, number(value)])) },
	]))
}

export function packingMode(config) {
	return config?.based_on_other_attribute_mapping && config?.packing_mode ? config.packing_mode : null
}

export function packingRatio(config) {
	return Object.fromEntries((config?.packing_size_details || []).map((row) => [row.attribute_value, row.quantity]))
}

export function batchPiecesPerBox(batch, sizes) {
	return sizes.reduce((sum, size) => sum + number(batch.ratio?.[size]), 0)
}

export function ratiosValid(batches, sizes, combo) {
	return batches.every((batch) => batchPiecesPerBox(batch, sizes) === number(combo))
}

export function coloursValid(batches, colours) {
	return batches.every((batch) => colours.includes(batch.colour))
}

function emptySizes(sizes) {
	return Object.fromEntries(sizes.map((size) => [size, 0]))
}

export function grnBoxQuantities(mode, sizes, state) {
	const out = emptySizes(sizes)
	if (mode === "Size Ratio Packing") {
		for (const batch of state.batches || []) for (const size of sizes) out[size] += number(batch.box_quantity) * number(batch.ratio?.[size])
	} else if (mode === "Size Wise Packing") {
		for (const row of Object.values(state.colourSize || {})) for (const size of sizes) out[size] += number(row[size])
	} else {
		for (const size of sizes) out[size] = number(state.flat?.[size])
	}
	return out
}

function batchPieces(batch, boxes, size) {
	return number(boxes) * number(batch.ratio?.[size])
}

export function dispatchBySize({ dynamic = false, mode = null, sizes, config = {}, legacy = {}, colourBoxes = {}, colourSize = {}, batches = [], batchBoxes = {} }) {
	const out = emptySizes(sizes)
	if (dynamic) {
		for (const batch of batches) for (const size of sizes) out[size] += batchPieces(batch, batchBoxes[batch.batch_row], size)
	} else if (mode === "Size Ratio Packing") {
		const ratio = packingRatio(config)
		const combo = number(config.packing_combo) || 1
		for (const boxes of Object.values(colourBoxes)) for (const size of sizes) out[size] += number(boxes) * number(ratio[size]) / combo
	} else if (mode === "Size Wise Packing") {
		for (const row of Object.values(colourSize)) for (const size of sizes) out[size] += number(row[size])
	} else {
		for (const size of sizes) out[size] = number(legacy[size])
	}
	return out
}

export function colourDetails({ dynamic = false, mode = null, sizes, config = {}, colourBoxes = {}, colourSize = {}, batches = [], batchBoxes = {} }) {
	const out = {}
	if (dynamic) {
		for (const batch of batches) {
			if (!number(batchBoxes[batch.batch_row])) continue
			out[batch.colour] ||= {}
			for (const size of sizes) {
				const pieces = batchPieces(batch, batchBoxes[batch.batch_row], size)
				if (pieces) out[batch.colour][size] = (out[batch.colour][size] || 0) + pieces
			}
		}
	} else if (mode === "Size Ratio Packing") {
		const ratio = packingRatio(config)
		const combo = number(config.packing_combo) || 1
		for (const [colour, boxes] of Object.entries(colourBoxes)) {
			if (number(boxes) <= 0) continue
			out[colour] = Object.fromEntries(sizes.map((size) => [size, round3(number(boxes) * number(ratio[size]) / combo)]))
		}
	} else if (mode === "Size Wise Packing") {
		for (const [colour, row] of Object.entries(colourSize)) {
			const values = Object.fromEntries(sizes.filter((size) => number(row[size])).map((size) => [size, number(row[size])]))
			if (Object.keys(values).length) out[colour] = values
		}
	}
	return out
}

export function lotTransferKey(row) {
	return `${row.source_fp}|${row.lot}|${row.warehouse}`
}

export function lotTransferPayload(rows, transfers) {
	return rows.map((row) => ({
		source_fp: row.source_fp,
		lot: row.lot,
		warehouse: row.warehouse,
		colours: transfers[lotTransferKey(row)] || {},
	}))
}

function transferCellErrors(cell, values, colour, size) {
	return [["loose_piece", "balance_loose_piece", "Transfer Loose Piece"], ["loose_piece_set", "balance_loose_piece_set", "Transfer Loose Piece Set"]]
		.filter(([field, balance]) => number(cell[field]) > number(values?.[balance]))
		.map(([field, balance, label]) => `${label} (${number(cell[field])}) exceeds available (${number(values?.[balance])}) for ${colour} / ${size}`)
}

export function lotTransferErrors(rows, transfers) {
	const errors = []
	for (const row of rows) {
		for (const [colour, entry] of Object.entries(transfers[lotTransferKey(row)] || {})) {
			let moved = 0
			for (const [size, cell] of Object.entries(entry.sizes || {})) {
				errors.push(...transferCellErrors(cell, row.old_lot_inward?.data?.[colour]?.values?.[size], colour, size))
				moved += number(cell.loose_piece) + number(cell.loose_piece_set)
			}
			if (moved > 0 && !entry.set_combination) errors.push("Please mention Set Colour")
		}
	}
	return errors
}

/** Server sends `sizes` in Item mapping order; object keys would put numeric sizes first. */
export function dispatchRowSizes(row) {
	return row.sizes || Object.keys(row.values || {})
}

export function dispatchEntrySource(row) {
	const sizes = dispatchRowSizes(row)
	return {
		sizes,
		packed: {
			sizes: Object.fromEntries(sizes.map((size) => [size, { packed: number(row.values[size]?.qty), dispatched: 0 }])),
			total_packed: number(row.total?.total_qty),
			total_dispatched: 0,
			dynamic_ratio_packing: Boolean(row.dynamic_ratio_packing),
			packing_batches: row.packing_batches || [],
		},
	}
}

export function dispatchInitialState(row) {
	const sizes = dispatchRowSizes(row)
	const colours = row.packing_config?.colours || []
	const grid = row.colour_grid || {}
	const mode = packingMode(row.packing_config)
	return {
		legacy: Object.fromEntries(sizes.map((size) => [size, number(row.values[size]?.dispatch_qty)])),
		batchBoxes: Object.fromEntries((row.batch_dispatches || []).map((batch) => [batch.batch_row, number(batch.box_quantity)])),
		colourBoxes: Object.fromEntries(colours.map((colour) => [colour, mode === "Size Ratio Packing" ? round3(Object.values(grid[colour] || {}).reduce((sum, value) => sum + number(value), 0)) : 0])),
		colourSize: Object.fromEntries(colours.map((colour) => [colour, Object.fromEntries(sizes.map((size) => [size, mode === "Size Wise Packing" ? number(grid[colour]?.[size]) : 0]))])),
	}
}
