/** View models for the Finishing Plan tabs; colour and total rules follow the Frappe 15 Desk views. */

export function differenceTone(value, zeroTone = "zero") {
	const number = Number(value || 0)
	if (number < 0) return "negative"
	if (number > 0) return "positive"
	return zeroTone
}

export function colourLabel(key) {
	return String(key || "").split("@")[0].trim()
}

function amount(value) {
	return Number(value ?? 0) || 0
}

function cell(value, toneRule) {
	return toneRule ? { value, tone: differenceTone(value, toneRule) } : { value }
}

function metricRow(metric, sizes, valueAt, totalValue) {
	return {
		label: metric.label,
		tone: metric.tone,
		cells: sizes.map((size) => cell(amount(valueAt(size)), metric.tone)),
		total: cell(amount(totalValue), metric.tone),
	}
}

function colourGroups(block, sizes, metrics) {
	return Object.entries(block?.data || {}).map(([key, colour], index) => ({
		key,
		index: index + 1,
		colour: colourLabel(key),
		part: colour.part || "",
		rows: metrics.map((metric) => metricRow(
			metric,
			sizes,
			(size) => colour.values?.[size]?.[metric.key],
			typeof colour.colour_total === "object" ? colour.colour_total?.[metric.key] : colour.colour_total,
		)),
	}))
}

function matrix(payload, groups) {
	return {
		sizes: payload.primary_values || [],
		setAttr: payload.is_set_item ? payload.set_attr || "Part" : "",
		groups,
		source: payload,
	}
}

export function detailsMatrix(payload) {
	const sizes = payload.primary_values || []
	const process = payload.process || ""
	const metrics = [
		{ key: "cutting", label: "Cutting Qty" },
		{ key: "delivered", label: `${process} Delivered`.trim() },
		{ key: "cut_sew_diff", label: "Difference", tone: "zero" },
		{ key: "delivered", label: `${process} Delivered`.trim() },
		{ key: "received", label: `${process} Received`.trim() },
		{ key: "difference", label: "Difference", tone: "zero" },
	]
	const block = payload.data || {}
	const totals = Object.entries(block.total || {}).map(([part, values]) => ({
		key: `total-${part}`,
		index: "",
		colour: "Total",
		part,
		total: true,
		rows: metrics.map((metric) => metricRow(metric, sizes, (size) => values?.[size]?.[metric.key], block.over_all?.[part]?.[metric.key])),
	}))
	return matrix(payload, [...colourGroups(block, sizes, metrics), ...totals])
}

export function quantityMatrix(payload) {
	const metrics = [
		{ key: "accepted", label: "Accepted" },
		{ key: "dc_qty", label: "Delivered" },
		{ key: "balance", label: "Balance" },
		{ key: "return_qty", label: "Loose Piece" },
		{ key: "pack_return", label: "Loose Piece Packed" },
	]
	return matrix(payload, colourGroups(payload.data, payload.primary_values || [], metrics))
}

export function reworkMatrix(payload) {
	const metrics = [
		{ key: "rework_qty", label: "Rework Quantity" },
		{ key: "reworked", label: "Reworked" },
		{ key: "pending", label: "Pending" },
		{ key: "rejected", label: "Rejected" },
	]
	return matrix(payload, colourGroups(payload.rework_details, payload.primary_values || [], metrics))
}

export function inwardMatrix(payload) {
	const metrics = [
		{ key: "accepted", label: "Accepted" },
		{ key: "reworked", label: "Reworked" },
		{ key: "rejected", label: "Rejected" },
		{ key: "pending", label: "Pending", tone: "zero-inward" },
	]
	return matrix(payload, colourGroups(payload.data, payload.primary_values || [], metrics))
}

export function singleMetricMatrix(payload, key) {
	const sizes = payload.primary_values || []
	const metric = { key, label: "" }
	const block = payload.data || {}
	const pick = (value) => (typeof value === "object" && value !== null ? value[key] : value)
	const total = {
		key: "total",
		index: "",
		colour: "Total",
		part: "",
		total: true,
		rows: [metricRow(metric, sizes, (size) => pick(block.total?.[size]), pick(block.total_qty))],
	}
	return matrix(payload, [...colourGroups(block, sizes, [metric]), total])
}

export function packedRows(payload) {
	const sizes = payload.primary_values || []
	const packed = payload.packed || {}
	const dynamic = Boolean(packed.dynamic_ratio_packing)
	const value = (size, key) => amount(packed.sizes?.[size]?.[key])
	const totalPacked = amount(packed.total_packed)
	const totalDispatched = amount(packed.total_dispatched)
	return [
		{ label: dynamic ? "Packed Pieces" : "Packed", cells: sizes.map((size) => value(size, "packed")), total: totalPacked },
		{ label: dynamic ? "Dispatched Pieces" : "Dispatched", cells: sizes.map((size) => value(size, "dispatched")), total: totalDispatched },
		{ label: "Balance", cells: sizes.map((size) => value(size, "packed") - value(size, "dispatched")), total: totalPacked - totalDispatched },
	]
}

export function percentage(base, part, positive = false) {
	let result = (amount(part) / amount(base)) * 100
	if (!Number.isFinite(result)) result = 0
	if (positive && result < 0) result *= -1
	return Number.parseFloat(result.toFixed(2))
}

const OCR_ROWS = [
	{ label: "Cutting Qty ( A )", key: "cutting_qty", totalKey: "cutting" },
	{ label: "Sewing Received ( B )", key: "sewing_received" },
	{ label: "Difference ( A - B )", compute: (v) => v.sewing_received - v.cutting_qty, tone: true },
	{ label: "Sewing Received ( C )", key: "sewing_received" },
	{ label: "Old Lot ( D1 )", key: "old_lot" },
	{ label: "Ironing Excess ( D2 )", key: "ironing_excess" },
	{ label: "Total Inward (D) (C + D1 + D2)", key: "total_inward" },
	{ label: "Finishing Inward ( E )", key: "dc_qty" },
	{ label: "Transferred ( F )", key: "transferred" },
	{ label: "Transferred as Loose Piece ( F1 )", key: "transferred_as_loose_piece" },
	{ label: "Difference ( (E + F) - D )", compute: (v) => v.transferred + v.dc_qty - v.total_inward, tone: true },
	{ label: "Packed Box", key: "packed_box" },
	{ label: "Packed Box Qty(In Pieces) ( G )", key: "packed_box_qty" },
	{ label: "Difference ( G - E )", compute: (v) => v.packed_box_qty - v.dc_qty, tone: true },
	{ label: "Dispatched Box", key: "dispatched_box" },
	{ label: "Dispatched Piece(In Pieces) ( H )", key: "dispatched_piece" },
	{ label: "Difference ( H - G )", compute: (v) => v.dispatched_piece - v.packed_box_qty, tone: true },
	{ label: "Order Qty ( O )", key: "order_qty" },
	{ label: "Order to Dispatch Diff ( O - H )", compute: (v) => v.order_qty - v.dispatched_piece, tone: true },
]

const OCR_BREAKDOWNS = [
	{ label: "Rejection Pieces ( I )", key: "rejected" },
	{ label: "Loose Piece ( J )", key: "loose_piece" },
	{ label: "Loose Piece Set ( K )", key: "loose_piece_set" },
	{ label: "Rework Pieces ( L )", key: "pending" },
]

const OCR_KEYS = ["cutting_qty", "sewing_received", "old_lot", "ironing_excess", "total_inward", "dc_qty", "transferred", "transferred_as_loose_piece", "packed_box", "packed_box_qty", "dispatched_box", "dispatched_piece", "order_qty", "rejected", "loose_piece", "loose_piece_set", "pending"]

function ocrValues(source, cuttingKey) {
	const values = Object.fromEntries(OCR_KEYS.map((key) => [key, amount(source?.[key])]))
	values.cutting_qty = amount(source?.[cuttingKey])
	return values
}

function ocrCell(row, values) {
	const value = row.compute ? row.compute(values) : values[row.key]
	return row.tone ? cell(value, "zero") : { value }
}

function unaccountable(v) {
	return (v.packed_box_qty + v.rejected + v.loose_piece_set + v.loose_piece + v.pending + v.transferred + v.transferred_as_loose_piece)
		- (v.sewing_received + v.old_lot + v.ironing_excess)
}

function ocrPercentages(v) {
	const produced = v.cutting_qty + v.old_lot + v.ironing_excess
	const cutToDispatch = percentage(produced - v.transferred - v.transferred_as_loose_piece, v.dispatched_piece)
	const loose = percentage(produced, v.loose_piece + v.loose_piece_set)
	const rejection = percentage(produced, v.rejected)
	const rework = percentage(produced, v.pending)
	const notReceived = percentage(produced, v.sewing_received - v.cutting_qty, true)
	const complete = cutToDispatch + loose + rejection + rework + notReceived
	const withDifference = (label, value) => ({ label, value, difference: (100 - value).toFixed(2) })
	return [
		withDifference("Cut to Dispatch", cutToDispatch),
		withDifference("Cut to Inward", percentage(v.cutting_qty, v.sewing_received)),
		withDifference("Inward to Dispatch", percentage(v.sewing_received + v.old_lot + v.ironing_excess - v.transferred - v.transferred_as_loose_piece, v.dispatched_piece)),
		withDifference("Order to Dispatch", percentage(v.order_qty, v.dispatched_piece)),
		{ label: "Loose Piece", value: loose, difference: "" },
		{ label: "Rejection", value: rejection, difference: "" },
		{ label: "Rework", value: rework, difference: "" },
		{ label: "Finishing Not Received", value: notReceived, difference: "" },
		{ label: "OCR Complete", value: complete.toFixed(2), difference: (100 - complete).toFixed(2) },
		{ label: "Unaccountable", value: `-${percentage(produced, -unaccountable(v), true)}`, difference: "" },
	]
}

export function ocrModel(part, sizes) {
	const totals = ocrValues(part, "cutting")
	const sizeValues = sizes.map((size) => ocrValues(part?.total?.[size], "cutting_qty"))
	const colours = Object.entries(part?.data || {})
	return {
		summary: OCR_ROWS.map((row) => ({
			label: row.label,
			cells: sizeValues.map((values) => ocrCell(row, values)),
			total: ocrCell(row, totals),
		})),
		breakdowns: OCR_BREAKDOWNS.map((section) => ({
			label: section.label,
			rows: colours.map(([key, colour]) => ({
				colour: colourLabel(key),
				cells: sizes.map((size) => ({ value: amount(colour.values?.[size]?.[section.key]) || null })),
				total: amount(colour.colour_total?.[section.key]),
			})),
			total: { cells: sizeValues.map((values) => values[section.key]), total: totals[section.key] },
		})),
		unaccountable: {
			label: "Unaccountable (( F + F1 + G + I + J + K + L ) - (B + D1 + D2 ))",
			cells: sizeValues.map((values) => cell(unaccountable(values), "zero")),
			total: cell(unaccountable(totals), "zero"),
		},
		percentages: ocrPercentages(totals),
	}
}

export function formatQuantity(value) {
	if (value === null || value === undefined || value === "") return "--"
	const number = Number(value)
	if (!Number.isFinite(number)) return String(value)
	return number.toLocaleString("en-IN", { maximumFractionDigits: 3 })
}
