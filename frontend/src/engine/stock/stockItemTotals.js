const precisionFactor = 1000

const metricReaders = {
	qty: (cell) => cell?.qty,
	secondary_qty: (cell) => cell?.secondary_qty,
	received_qty: (cell) => cell?.received_qty ?? cell?.received_quantity,
	pending_qty: (cell) => cell?.pending_qty ?? cell?.pending_quantity,
	amount: (cell) => cellAmount(cell),
}

export function roundQuantity(value) {
	return Math.round((Number(value) || 0) * precisionFactor) / precisionFactor
}

export function cellAmount(cell) {
	return Number(cell?.total_amount ?? cell?.amount ?? (Number(cell?.qty || 0) * Number(cell?.rate || 0)))
}

export function rowAmount(row) {
	return Object.values(row?.values || {}).reduce((total, cell) => total + cellAmount(cell), 0)
}

function emptyMetrics() {
	return Object.fromEntries(Object.keys(metricReaders).map((key) => [key, 0]))
}

function addCell(target, cell) {
	for (const [key, read] of Object.entries(metricReaders)) target[key] += Number(read(cell) || 0)
}

function roundMetrics(metrics, hasSecondary) {
	const rounded = Object.fromEntries(Object.entries(metrics).map(([key, value]) => [key, roundQuantity(value)]))
	if (!hasSecondary) rounded.secondary_qty = 0
	return rounded
}

function finishBucket(bucket) {
	const secondaryUom = bucket.secondaryUoms.size === 1 ? [...bucket.secondaryUoms][0] : ""
	return {
		uom: bucket.uom,
		secondary_uom: secondaryUom,
		values: Object.fromEntries(Object.entries(bucket.values).map(([key, metrics]) => [key, roundMetrics(metrics, Boolean(secondaryUom))])),
		total: roundMetrics(bucket.total, Boolean(secondaryUom)),
	}
}

/** Column totals of `items` for `valueKeys`, one entry per stock UOM so different units are never added together. */
export function getUomTotals(items, valueKeys) {
	const buckets = new Map()
	for (const row of items || []) {
		const uom = row.default_uom || ""
		if (!buckets.has(uom)) {
			buckets.set(uom, { uom, secondaryUoms: new Set(), total: emptyMetrics(), values: Object.fromEntries(valueKeys.map((key) => [key, emptyMetrics()])) })
		}
		const bucket = buckets.get(uom)
		for (const key of valueKeys) {
			const cell = row.values?.[key]
			if (!cell) continue
			addCell(bucket.values[key], cell)
			addCell(bucket.total, cell)
			if (Number(cell.secondary_qty || 0)) bucket.secondaryUoms.add(cell.secondary_uom || row.secondary_uom || "")
		}
	}
	return [...buckets.values()].map(finishBucket)
}

/** Running total of one item's size entry: quantity, and value when rates are entered. */
export function getEntryTotals(quantities, rates, valueKeys) {
	let qty = 0
	let amount = 0
	for (const key of valueKeys) {
		const quantity = Number(quantities?.[key] || 0)
		qty += quantity
		amount += quantity * Number(rates?.[key] || 0)
	}
	return { qty: roundQuantity(qty), amount: roundQuantity(amount) }
}
