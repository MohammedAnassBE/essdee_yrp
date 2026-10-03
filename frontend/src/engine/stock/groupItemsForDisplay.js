// Essdee /web display aggregation for route-split stock rows.
const ADDITIVE_FIELDS = new Set([
	"qty",
	"pending_quantity",
	"pending_qty",
	"max_receivable_quantity",
	"delivered_quantity",
	"received_quantity",
	"stock_qty",
	"stock_update",
	"amount",
	"total_cost",
	"secondary_qty",
	"cancelled_quantity",
	"cancelled_qty",
])

const ROUTE_ONLY_FIELDS = new Set([
	"fabric_reference_variant",
	"fabric_reference_allocations",
	"additional_parameters",
	"source_grn",
	"source_grn_item",
	"ref_doctype",
	"ref_docname",
	"delivery_challan_item",
	"row_index",
	"table_index",
])

const DISPLAY_SOURCE_ITEMS = Symbol("displaySourceItems")

function clone(value) {
	// Vue stores loaded table rows as reactive Proxy objects. Browsers expose
	// structuredClone(), but it throws DataCloneError for a Proxy and prevents
	// the entire grouped table from rendering. JSON data is the editor's actual
	// contract, so a JSON clone is both sufficient and Proxy-safe.
	return JSON.parse(JSON.stringify(value))
}

function canonical(value) {
	if (Array.isArray(value)) return value.map(canonical)
	if (value && typeof value === "object") {
		return Object.fromEntries(
			Object.keys(value).sort().map((key) => [key, canonical(value[key])]),
		)
	}
	return value
}

function add(left, right) {
	return Math.round(((Number(left) || 0) + (Number(right) || 0)) * 1e9) / 1e9
}

function displayIdentity(item) {
	const entry = {}
	for (const [key, value] of Object.entries(item || {})) {
		if (key === "values" || ADDITIVE_FIELDS.has(key) || ROUTE_ONLY_FIELDS.has(key)) continue
		entry[key] = value
	}

	const values = {}
	for (const [primaryValue, cell] of Object.entries(item?.values || {})) {
		values[primaryValue] = Object.fromEntries(
			Object.entries(cell || {}).filter(
				([key]) => !ADDITIVE_FIELDS.has(key) && !ROUTE_ONLY_FIELDS.has(key),
			),
		)
	}
	return JSON.stringify(canonical({ entry, values }))
}

function mergeAdditiveFields(target, source) {
	for (const fieldname of ADDITIVE_FIELDS) {
		if (
			Object.prototype.hasOwnProperty.call(target || {}, fieldname)
			|| Object.prototype.hasOwnProperty.call(source || {}, fieldname)
		) {
			target[fieldname] = add(target[fieldname], source[fieldname])
		}
	}
}

/**
 * Aggregate route-split Work Order/DC rows into physical items for presentation.
 *
 * Fabric calculations intentionally retain one flat child row per
 * `fabric_reference_variant`, because later cloth-program tracking needs that
 * route reference. The item editor does not need to repeat the same physical
 * yarn/cloth variant once per route, so this function sums display-equivalent
 * entries. Hidden source references let editable DC totals be distributed back
 * to the original grouped rows without leaking helper metadata into the payload.
 */
export function groupItemsForDisplay(groups) {
	return (groups || []).map((group) => {
		const byIdentity = new Map()
		const items = []

		for (const source of group.items || []) {
			const identity = displayIdentity(source)
			let target = byIdentity.get(identity)
			if (!target) {
				target = clone(source)
				for (const fieldname of ROUTE_ONLY_FIELDS) delete target[fieldname]
				for (const cell of Object.values(target.values || {})) {
					for (const fieldname of ROUTE_ONLY_FIELDS) delete cell[fieldname]
				}
				Object.defineProperty(target, DISPLAY_SOURCE_ITEMS, {
					value: [source],
					enumerable: false,
				})
				byIdentity.set(identity, target)
				items.push(target)
				continue
			}

			target[DISPLAY_SOURCE_ITEMS].push(source)
			mergeAdditiveFields(target, source)
			for (const [primaryValue, sourceCell] of Object.entries(source.values || {})) {
				if (!target.values[primaryValue]) {
					target.values[primaryValue] = clone(sourceCell)
					continue
				}
				mergeAdditiveFields(target.values[primaryValue], sourceCell)
			}
		}

		return { ...clone(group), items }
	})
}

export function countItemsForDisplay(groups, aggregate = false) {
	const visibleGroups = aggregate ? groupItemsForDisplay(groups) : (groups || [])
	return visibleGroups.reduce((count, group) => count + (group.items?.length || 0), 0)
}

export function countCalculatedItemsForDisplay(groupedByField, fallback = {}) {
	const physicalCount = (fieldname) => {
		const groups = groupedByField?.[fieldname]
		return Array.isArray(groups)
			? countItemsForDisplay(groups, true)
			: Number(fallback?.[fieldname]) || 0
	}
	return {
		deliverables: physicalCount("deliverables"),
		receivables: physicalCount("receivables"),
	}
}

export function sumItemQuantities(groups, precision = 3) {
	let total = 0
	for (const group of groups || []) {
		for (const item of group.items || []) {
			for (const cell of Object.values(item.values || {})) {
				total += Number(cell?.qty) || 0
			}
		}
	}
	const factor = 10 ** precision
	return Math.round(total * factor) / factor
}

function roundQty(value) {
	return Math.round((Number(value) || 0) * 1000) / 1000
}

export function setAggregatedCellQuantity(displayItem, primaryValue, value) {
	const sources = displayItem?.[DISPLAY_SOURCE_ITEMS] || [displayItem]
	const cells = sources
		.map((item) => item?.values?.[primaryValue])
		.filter(Boolean)
	if (!cells.length) return

	const total = Math.max(roundQty(value), 0)
	let weights = cells.map((cell) => Math.max(Number(cell.pending_quantity) || 0, 0))
	let weightTotal = weights.reduce((sum, weight) => sum + weight, 0)
	if (!weightTotal) {
		weights = cells.map((cell) => Math.max(Number(cell.qty) || 0, 0))
		weightTotal = weights.reduce((sum, weight) => sum + weight, 0)
	}
	if (!weightTotal) {
		weights = cells.map(() => 1)
		weightTotal = cells.length
	}

	let allocated = 0
	for (let index = 0; index < cells.length; index += 1) {
		const qty = index === cells.length - 1
			? roundQty(total - allocated)
			: roundQty(total * weights[index] / weightTotal)
		cells[index].qty = qty
		allocated = roundQty(allocated + qty)
	}
}

export function setAggregatedItemField(displayItem, fieldname, value) {
	const sources = displayItem?.[DISPLAY_SOURCE_ITEMS] || [displayItem]
	for (const source of sources) source[fieldname] = value
}
