/** Frappe 15 Finishing Plan create dialogs: fields, matrices and the payload each command receives. */

import { entryQuantities } from "./finishingEntries.js"

const qtyReference = [{ key: "balance", label: "Qty" }]

export const ENTRY_DEFINITIONS = {
	create_delivery_challan: { label: "Create DC", title: "Enter Quantity to Create DC", submit: "Create DC", source: "item_details", fields: ["from_location", "actual_date"], typeSelect: true, inputLabel: "DC Qty", checkable: true },
	return_items: { label: "Return Item", title: "Return Items", submit: "Return", source: "item_details", fields: ["received_type"], references: [{ key: "dc_qty", label: "Delivered" }], inputLabel: "Quantity" },
	convert_to_loose_piece: { label: "Convert to Loose Piece", title: "Convert Items to Loose Piece", submit: "Convert", source: "item_details", fields: ["from_location"], references: [{ key: "balance", label: "Balance Qty" }], inputLabel: "Quantity" },
	create_grn: { label: "Make GRN", title: "Create Goods Received Note", submit: "Create GRN", source: "grn", fields: ["delivery_location", "actual_date"], component: "packing" },
	dispatch_box: { label: "Dispatch Box", title: "Dispatch Box", submit: "Dispatch", source: "grn", fields: ["from_location", "to_location", "goods_value", "vehicle_no"], component: "dispatch" },
	add_ironing_excess: { label: "Add Ironing Excess Qty", title: "Add Ironing Excess Pieces", submit: "Create", source: "ironing_excess", fields: [], references: [], inputLabel: "Ironing Excess" },
	return_pack: { label: "Return Pack", title: "Add Pack Return Pieces", submit: "Create", source: "pack_return", fields: [], references: [], inputLabel: "Pack Return" },
	create_alternative_plan: { label: "Create Alternative Plan", title: "Select Alternative Item and IPD", submit: "Next", source: "item_details", fields: ["lot_source", "lot_name", "existing_lot", "alternative_item", "production_detail"], references: qtyReference, inputLabel: "Conversion Qty", checkable: true },
	update_alternative_quantity: { label: "Update Quantity", title: "Update Alternate Lot Quantity", submit: "Update", source: "item_details", fields: ["target_lot"], references: qtyReference, inputLabel: "Conversion Qty", checkable: true },
}

const FIELD_LABELS = {
	from_location: "From Location",
	to_location: "To Location",
	delivery_location: "Delivery Location",
	actual_date: "Actual Date",
	received_type: "Received Type",
	goods_value: "Goods Value",
	vehicle_no: "Vehicle No",
	lot_source: "Lot Source",
	lot_name: "Lot Name",
	existing_lot: "Existing Lot",
	alternative_item: "Alternative Item",
	production_detail: "Item Production Detail",
	target_lot: "Target Lot",
}

export function missingFields(fields, form) {
	return fields.filter((field) => form[field] === null || form[field] === undefined || form[field] === "").map((field) => FIELD_LABELS[field])
}

function visibleValues(action, form) {
	const fields = ENTRY_DEFINITIONS[action].fields.filter((field) => {
		if (field === "lot_name") return form.lot_source !== "Existing Lot"
		if (field === "existing_lot") return form.lot_source === "Existing Lot"
		return true
	})
	return Object.fromEntries(fields.map((field) => [field, form[field]]))
}

export function entryPayload(action, form, entry, customValues = null, requestId = "") {
	const values = visibleValues(action, form)
	if (ENTRY_DEFINITIONS[action].typeSelect) values.selected_type = form.selected_type
	if (customValues) {
		Object.assign(values, customValues)
		if (action === "create_grn") values.request_id = requestId
		return values
	}
	return { ...values, quantities: entryQuantities(entry) }
}
