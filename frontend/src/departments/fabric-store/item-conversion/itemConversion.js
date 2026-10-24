/** Pure Item Conversion rules shared by the /web editor and its tests. */

export const SIDE_LABELS = { from: "From", to: "To" }
export const ITEM_FILTERS = { is_stock_item: 1, disabled: 0, variant_of: ["is", "not set"] }
const RATE_DIGITS = 9

export function emptySide(side = {}) {
	return {
		item: "",
		attributes: {},
		primary_value: "",
		lot: "",
		received_type: "",
		qty: null,
		secondary_qty: null,
		remarks: "",
		rate: 0,
		...JSON.parse(JSON.stringify(side || {})),
	}
}

/** The dependent attribute's row (Stage) for the side's chosen value: its attributes, sizes and UOM. */
export function stageDetails(schema, side) {
	const dependent = schema?.dependent_attribute
	return dependent ? schema.dependent_attribute_details?.attr_list?.[side?.attributes?.[dependent]] || null : null
}

/** Attributes the side's variant takes: all of them, or the dependent attribute plus those its chosen value lists. */
export function sideAttributes(schema, side) {
	const all = schema?.attributes || []
	const dependent = schema?.dependent_attribute
	if (!dependent || !all.includes(dependent)) return all
	const stage = stageDetails(schema, side)
	return all.filter((attribute) => attribute === dependent || stage?.attributes?.includes(attribute))
}

export function sideUom(schema, side) {
	return stageDetails(schema, side)?.uom || schema?.default_uom || side?.uom || ""
}

export function sizeOptions(schema, side) {
	return stageDetails(schema, side)?.primary_attribute_values || schema?.primary_attribute_values || []
}

/** Set one attribute and drop the ones the new dependent value no longer takes. */
export function withAttribute(schema, side, attribute, value) {
	const next = { ...side, attributes: { ...(side.attributes || {}), [attribute]: value } }
	const allowed = new Set(sideAttributes(schema, next))
	next.attributes = Object.fromEntries(Object.entries(next.attributes).filter(([key]) => allowed.has(key)))
	return next
}

/** Problems that stop one side from saving: one item, its attributes, one size, lot, received type and a quantity. */
export function sideProblems(side, schema, direction) {
	const label = SIDE_LABELS[direction]
	if (!side?.item) return [`Select the ${label} Item.`]
	const problems = []
	for (const attribute of sideAttributes(schema, side)) {
		if (!side.attributes?.[attribute]) problems.push(`Select the ${label} ${attribute}.`)
	}
	if (schema?.primary_attribute && !side.primary_value) problems.push(`Select the ${label} ${schema.primary_attribute}.`)
	if (!side.lot) problems.push(`Select the ${label} Lot.`)
	if (!side.received_type) problems.push(`Select the ${label} Received Type.`)
	if (!(Number(side.qty) > 0)) problems.push(`Enter the ${label} Quantity.`)
	return problems
}

/** Arguments for the From valuation rate lookup, or null until the variant and location are known. */
export function valuationArgs(side, schema, header) {
	if (!schema || !header?.warehouse || sideProblems({ ...side, qty: 1 }, schema, "from").length) return null
	const attributes = Object.fromEntries(sideAttributes(schema, side).map((attribute) => [attribute, side.attributes[attribute]]))
	if (schema.primary_attribute) attributes[schema.primary_attribute] = side.primary_value
	return {
		item: side.item,
		attributes: JSON.stringify(attributes),
		lot: side.lot,
		received_type: side.received_type,
		uom: sideUom(schema, side),
		warehouse: header.warehouse,
		posting_date: header.posting_date,
		posting_time: header.posting_time,
	}
}

/** From value at the stock valuation rate; the single To row takes that value spread over its quantity. */
export function conversionPreview(fromSide, toSide) {
	const fromValue = Number(fromSide?.qty || 0) * Number(fromSide?.rate || 0)
	const toQty = Number(toSide?.qty || 0)
	const toRate = toQty > 0 ? Number((fromValue / toQty).toFixed(RATE_DIGITS)) : 0
	const toValue = toRate * toQty
	return { fromValue, toRate, toValue, difference: Math.round((fromValue - toValue) * 100) / 100 }
}

/** The side fields the server accepts. */
export function sideSaveValues(side) {
	const { item, attributes, primary_value, lot, received_type, qty, secondary_qty, remarks } = side || {}
	return { item, attributes: { ...(attributes || {}) }, primary_value: primary_value || null, lot, received_type, qty: Number(qty || 0), secondary_qty: Number(secondary_qty || 0), remarks: remarks || "" }
}

/** Fill the To lot and received type from From while To has none. */
export function inheritDimensions(fromSide, toSide) {
	return {
		...toSide,
		lot: toSide.lot || fromSide.lot || "",
		received_type: toSide.received_type || fromSide.received_type || "",
	}
}

export function formatAmount(value, maximumFractionDigits = 2) {
	return Number(value || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits })
}
