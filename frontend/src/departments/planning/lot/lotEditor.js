export const LOT_EDIT_GROUPS = [
	{ key: "order", eyebrow: "Lot", label: "Lot & order", fields: ["lot_name", "production_order", "item", "production_detail"] },
	{ key: "planning", eyebrow: "Planning", label: "Owner & schedule", fields: ["assigned_person", "season", "expected_delivery_date", "status"] },
	{ key: "production", eyebrow: "Production", label: "Production settings", fields: ["primary_item_attribute", "size_set_colour", "capacity_planning"] },
	{ key: "derived", eyebrow: "From IPD", label: "Derived from Item Production Detail", fields: ["uom", "pack_in_stage", "pack_out_stage", "packing_uom", "version", "cloth_excess_percentage", "total_order_quantity"] },
]
export const IPD_DERIVED_FIELDS = ["uom", "pack_in_stage", "packing_uom", "pack_out_stage", "dependent_attribute_mapping", "tech_pack_version", "pattern_version", "packing_combo"]
export const DERIVED_LABELS = { uom: "UOM", pack_in_stage: "Pack In Stage", pack_out_stage: "Pack Out Stage", packing_uom: "Packing UOM", version: "Version", cloth_excess_percentage: "Cloth Excess Percentage", total_order_quantity: "Total Order Quantity" }

export function editTabFor(tab) {
	return ["order-items", "order-details"].includes(tab) ? tab : "details"
}
export function lotEditorTabs(form, orderItemDetails, isNew) {
	return [
		{ key: "details", label: "Details", visible: true, count: null },
		{ key: "order-items", label: "Order Items", visible: Boolean(form.item && form.production_detail), count: null },
		{ key: "order-details", label: "Lot Order Details", visible: !isNew && Boolean(orderItemDetails.length), count: orderItemDetails.reduce((sum, group) => sum + group.items.length, 0) },
	].filter((tab) => tab.visible)
}
export function lotLinkFilters(fieldname, form) {
	if (fieldname === "production_order") return { docstatus: 1, ...(form.item ? { item: form.item } : {}) }
	if (fieldname === "production_detail") return { item: form.item }
	return undefined
}
export function fabricColumnFilters(column, row) {
	if (column.fieldname === "cloth_item") return { is_cloth_item: 1 }
	if (column.fieldname === "production_detail") return { item: row.cloth_item }
	return undefined
}
export function clearedLotContext(fieldname, form, derived) {
	const values = { ...form, [fieldname]: "" }
	if (fieldname === "production_order") Object.assign(values, { item: "", production_detail: "" })
	const clearsDerived = ["production_order", "production_detail"].includes(fieldname)
	return { form: values, derived: clearsDerived ? { ...derived, ...Object.fromEntries(IPD_DERIVED_FIELDS.map((key) => [key, ""])) } : derived, itemDetails: null }
}
export function lotSavePayload(form, itemDetails, orderItemDetails) {
	const fields = LOT_EDIT_GROUPS.filter((group) => group.key !== "derived").flatMap((group) => group.fields)
	return clone({ ...Object.fromEntries(fields.map((key) => [key, form[key]])), lot_fabric_details: form.lot_fabric_details,
		item_details: itemDetails ? [itemDetails] : [], order_item_details: orderItemDetails })
}
export function lotEditorCleanSignature(payload, signature) {
	return payload.item_details_generated ? "" : signature
}
export function lotOrderEntry(details) {
	const cells = { qty: 0, ratio: 0, mrp: 0 }
	return { attributes: Object.fromEntries((details.final_state_attr || []).map((key) => [key, ""])),
		values: details.primary_attribute ? Object.fromEntries(details.primary_attribute_values.map((size) => [size, { ...cells }])) : cells }
}
export function addLotOrderRow(itemDetails, entry) {
	const attributes = Object.fromEntries((itemDetails.final_state_attr || []).map((attribute) => {
		if (!entry.attributes[attribute]) throw new Error(`Enter value for ${attribute}`)
		return [attribute, entry.attributes[attribute]]
	}))
	const quantities = itemDetails.primary_attribute ? Object.values(entry.values).map((value) => value.qty) : [entry.values.qty]
	if (!quantities.some((quantity) => Number(quantity) > 0)) throw new Error("Fill the quantity")
	const result = clone(itemDetails)
	const existing = result.items.find((row) => deeplyEqual(row.attributes, attributes))
	if (existing) mergeOrderValues(existing.values, entry.values, Boolean(itemDetails.primary_attribute))
	else result.items.push({ attributes, primary_attribute: itemDetails.primary_attribute, values: clone(entry.values) })
	return result
}
function mergeOrderValues(stored, incoming, hasPrimaryAttribute) {
	if (!hasPrimaryAttribute) return Object.assign(stored, { qty: Number(stored.qty || 0) + Number(incoming.qty || 0), ratio: incoming.ratio, mrp: incoming.mrp })
	for (const size of Object.keys(stored)) mergeOrderValues(stored[size], incoming[size], false)
}
function deeplyEqual(first, second) {
	if (first === second) return true
	if (!first || !second || typeof first !== "object" || typeof second !== "object") return false
	const keys = Object.keys(first)
	return keys.length === Object.keys(second).length && keys.every((key) => Object.hasOwn(second, key) && deeplyEqual(first[key], second[key]))
}
export function boxOrderView(details) {
	return { item: details.item, uom: details.default_uom, attributes: details.final_state_attr || [],
		sizes: details.primary_attribute ? details.primary_attribute_values : [], items: details.items }
}
export function orderQuantityTotal(items, size = null) {
	return items.reduce((sum, item) => sum + (size ? Number(item.values[size]?.qty || 0) : Object.values(item.values).reduce((total, cell) => total + Number(cell.qty || 0), 0)), 0)
}
export function orderDetailsView(groups, version, colourAttribute) {
	return { colour_attribute: colourAttribute, stages: [{ key: "quantity", label: "Order" }], groups: groups.map((group) => {
		const sizes = group.primary_attribute ? group.primary_attribute_values : ["default"]
		return { ...group, sizes, items: group.items.map((item) => ({ ...item, colour_note: setColourNote(item, version),
			values: Object.fromEntries(sizes.map((size) => [size, { quantity: item.values[size]?.qty || 0 }])),
			totals: { quantity: orderQuantityTotal([item]) } })),
			size_totals: { quantity: Object.fromEntries(sizes.map((size) => [size, orderQuantityTotal(group.items, size)])) }, totals: { quantity: orderQuantityTotal(group.items) } }
	}) }
}
export function setColourNote(item, version) {
	return ["V2", "V3"].includes(version) && item.is_set_item && item.attributes[item.set_attr] !== item.major_attr_value ? item.item_keys.major_colour : null
}
export function clone(value) { return JSON.parse(JSON.stringify(value)) }
