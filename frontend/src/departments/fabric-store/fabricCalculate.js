const QUANTITY_PRECISION = 2
const QUANTITY_ROUNDING_RULE = roundHalfToEven
const CALCULATION_PRECISION = 3

function quantity(value) {
	return Number(value || 0)
}

function roundQuantity(value) {
	return QUANTITY_ROUNDING_RULE(value, QUANTITY_PRECISION)
}

/** Mirrors System Settings rounding_method "Banker's Rounding" and float_precision 2. */
function roundHalfToEven(value, precision) {
	if (value === 0) return 0
	const multiplier = 10 ** precision
	const scaled = Math.abs(value) * multiplier
	const floor = Math.floor(scaled)
	const decimal = scaled - floor
	const epsilon = 2 ** (Math.log2(Math.abs(scaled)) - 52)
	const isTie = epsilon < 0.5 ? Math.abs(decimal - 0.5) < epsilon : decimal === 0.5
	const rounded = isTie ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(scaled)
	return value < 0 ? -rounded / multiplier : rounded / multiplier
}

function roundCalculation(value) {
	const scale = 10 ** CALCULATION_PRECISION
	return Math.round(value * scale) / scale
}

function displayQuantity(value) {
	return quantity(value).toLocaleString("en-IN", { maximumFractionDigits: 3 })
}

export function fabricSourceProcess(context) {
	return context.source_process?.value || context.source_process_options?.[0]?.value || null
}

export function fabricUnavailableMessage(context) {
	if (!context.source_process?.unavailable) return ""
	const source = context.source_process
	return `Submit an unallocated ${source.label || source.process_name} GRN, then reopen Calculate.`
}

export function fabricEntryLabel(entry) {
	return entry.display_label || entry.label || Object.values(entry.out_attrs || {}).join(" · ") || entry.key
}

function hydrateEntry(source, index, colour, prefill, useInputPrefill = true) {
	const entry = {
		...source,
		input_key: `${source.key}:${colour || index}`,
		colour: colour || source.knit_colour,
		qty: roundQuantity(quantity(prefill)),
	}
	if (colour) entry.display_label = `${colour} · ${fabricEntryLabel(source)}`
	entry.inputs = (source.knitting_inputs || []).map((input) => {
		const inputPrefill = useInputPrefill ? input.prefill : null
		return { ...input, qty: roundQuantity(quantity(inputPrefill ?? entry.qty * quantity(input.qty_per_output))) }
	})
	return entry
}

function hydrateRow(source) {
	const row = { ...source }
	row.multi_colour = isMultiColour(row)
	row.needs_colour = needsFabricColour(row)
	row.colour = row.needs_colour ? row.greige_colour || "" : ""
	row.entries = row.multi_colour
		? hydrateColourEntries(row)
		: (row.qty_rows || []).map((entry, index) => hydrateEntry(entry, index, null, entry.prefill))
	updateLegacyYarn(row)
	return row
}

function isMultiColour(row) {
	const colours = row.colour_options || []
	return row.kind === "knitting" && !row.reference_routed && row.has_colour && colours.length > 0 && colours.length <= 6
}

function hydrateColourEntries(row) {
	return row.colour_options.flatMap((colour) => {
		const isDefaultColour = colour === row.greige_colour
		return (row.qty_rows || []).map((entry, index) => (
			hydrateEntry(entry, index, colour, isDefaultColour ? entry.prefill : 0, isDefaultColour)
		))
	})
}

function needsFabricColour(row) {
	if (row.kind !== "knitting" || !row.has_colour || row.multi_colour) return false
	return !row.reference_routed || (row.qty_rows || []).some((entry) => !entry.knit_colour)
}

export function hydrateFabricRows(context) {
	return (context.rows || []).map(hydrateRow)
}

function updateLegacyYarn(row) {
	if (row.kind !== "knitting" || row.manual_io || row.reference_routed) return
	const total = row.entries.reduce((sum, entry) => sum + quantity(entry.qty), 0)
	row.yarn_qty = roundCalculation(total / (quantity(row.ratio) || 1))
}

export function setFabricClothQuantity(row, entry, value) {
	const next = roundQuantity(quantity(value))
	if (next === quantity(entry.qty)) return
	entry.qty = next
	if (row.manual_io) {
		for (const input of entry.inputs) input.qty = roundQuantity(roundCalculation(next * quantity(input.qty_per_output)))
	}
	updateLegacyYarn(row)
}

export function fabricEntryError(row, entry) {
	if (!row.manual_io) return ""
	const hasYarn = entry.inputs.some((input) => quantity(input.qty) > 0)
	if (quantity(entry.qty) <= 0 && hasYarn) return `Enter the expected cloth quantity for ${fabricEntryLabel(entry)}.`
	if (quantity(entry.qty) > 0 && !hasYarn) return `Enter at least one yarn deliverable quantity for ${fabricEntryLabel(entry)}.`
	return ""
}

export function fabricColourError(row) {
	if (row.kind !== "knitting" || !row.has_colour || row.colour) return ""
	const missing = row.entries.some((entry) => quantity(entry.qty) > 0 && !entry.colour)
	return missing ? `Select the cloth Colour for ${row.cloth_item}.` : ""
}

export function canCalculateFabric(context, rows) {
	if (context.source_process?.unavailable) return false
	if (rows.some((row) => fabricColourError(row) || row.entries.some((entry) => fabricEntryError(row, entry)))) return false
	return rows.some((row) => row.entries.some((entry) => quantity(entry.qty) > 0))
}

function buildEntry(entry, manual) {
	const line = { key: entry.key, matrix_key: entry.matrix_key || entry.key, out_attrs: entry.out_attrs, qty: roundQuantity(quantity(entry.qty)) }
	if (entry.colour) line.colour = entry.colour
	if (entry.source_bucket_key) line.source_bucket_key = entry.source_bucket_key
	if (entry.source_mode) line.source_mode = entry.source_mode
	if (manual) line.inputs = entry.inputs.map((input) => ({ key: input.key, qty: roundQuantity(quantity(input.qty)) }))
	return line
}

function buildRow(row) {
	return {
		fabric_row: row.fabric_row,
		colour: row.colour || null,
		yarn_qty: !row.manual_io && !row.reference_routed && (row.yarns || []).length <= 1 ? row.yarn_qty || null : null,
		entries: row.entries.filter((entry) => quantity(entry.qty) > 0).map((entry) => buildEntry(entry, row.manual_io)),
	}
}

export function buildFabricPayload(context, rows) {
	return { source_process: fabricSourceProcess(context), rows: rows.map(buildRow).filter((row) => row.entries.length) }
}

export function fabricPlanningHint(row, entry) {
	if (entry.source_process) return fabricSourceHint(entry)
	if (row.kind !== "knitting" || entry.program == null) return ""
	return `Program ${displayQuantity(entry.program)} · Ordered ${displayQuantity(entry.ordered)} · Balance ${displayQuantity(entry.balance)}`
}

function fabricSourceHint(entry) {
	if (entry.source_bucket_key) {
		const parts = [entry.source_grn || "Source GRN"]
		if (entry.source_grn_row) parts.push(`row ${entry.source_grn_row}`)
		if (entry.source_stock_available != null) parts.push(`${displayQuantity(entry.source_stock_available)} Kg available`)
		return parts.join(" · ")
	}
	const hint = `Available from ${entry.source_process} GRNs: ${displayQuantity(entry.source_available)} Kg`
	return entry.source_shared ? `${hint} · Shared input — allocate it across these rows` : hint
}

export function fabricYarnTotals(row) {
	if (!row.manual_io) return legacyYarnTotals(row)
	const items = new Map()
	for (const entry of row.entries) {
		for (const input of entry.inputs) items.set(input.item, (items.get(input.item) || 0) + quantity(input.qty))
	}
	return yarnTotals([...items].map(([item, total]) => ({ item, qty: total })))
}

function legacyYarnTotals(row) {
	const total = quantity(row.yarn_qty)
	const items = (row.yarns || []).map((yarn) => ({ item: yarn.yarn_item, qty: roundCalculation(total * quantity(yarn.ratio) / 100) }))
	return yarnTotals(items)
}

function yarnTotals(items) {
	return {
		items: items.map((item) => ({ ...item, qty: roundCalculation(item.qty) })),
		total: roundCalculation(items.reduce((sum, item) => sum + item.qty, 0)),
	}
}

function addDemand(groups, key, label, available, demand) {
	if (available == null) return
	if (!groups.has(key)) groups.set(key, { label, available: quantity(available), demand: 0 })
	groups.get(key).demand += demand
}

function addSourceDemand(groups, row, entry) {
	const key = entry.source_bucket_key || entry.source_pool_key
	if (!key) return
	const { available, demand } = sourceDemand(entry)
	addDemand(groups, key, entry.source_grn || `${row.cloth_item} · ${fabricEntryLabel(entry)}`, available, demand)
}

function sourceDemand(entry) {
	const hasStock = entry.source_stock_available != null
	const available = hasStock ? entry.source_stock_available : entry.source_available ?? entry.available
	const factor = hasStock ? quantity(entry.source_stock_per_output) || 1 : 1
	return { available, demand: quantity(entry.qty) * factor }
}

function balanceWarnings(row) {
	const groups = new Map()
	for (const entry of row.entries) {
		const route = entry.reference_item_variant || entry.out_attrs?.Dia || entry.label
		const routeLabel = entry.reference_item_variant ? fabricEntryLabel(entry) : route
		addDemand(groups, route, `${row.cloth_item} · ${routeLabel}`, entry.balance, quantity(entry.qty))
	}
	return demandWarnings(groups, "balance")
}

function demandWarnings(groups, limit) {
	return [...groups.values()].filter((group) => group.demand > group.available + 0.001)
		.map((group) => `${group.label}: ${displayQuantity(group.demand)} > ${limit} ${displayQuantity(group.available)}`)
}

export function fabricWarnings(rows) {
	const warnings = []
	const sources = new Map()
	for (const row of rows) {
		if (row.kind === "knitting") warnings.push(...balanceWarnings(row))
		else for (const entry of row.entries) addSourceDemand(sources, row, entry)
	}
	return [...warnings, ...demandWarnings(sources, "source GRN available")]
}
