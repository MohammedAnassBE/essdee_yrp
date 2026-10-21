const field = (fieldname, label, fieldtype = "Data", extra = {}) => ({ fieldname, label, fieldtype, ...extra })
const link = (fieldname, label, options, extra = {}) => field(fieldname, label, "Link", { options, ...extra })
const readonly = { read_only: 1 }

export const INSPECTION_FIELDS = {
	against_id: field("against_id", "Work Order", "Dynamic Link", { options: "against", reqd: 1, link_filters: { docstatus: 1 } }),
	item: link("item", "Item", "Item", readonly),
	lot: link("lot", "Lot", "SD YRP Lot", readonly),
	supplier: link("supplier", "Supplier", "Supplier", readonly),
	order_qty: field("order_qty", "Order Qty", "Int", readonly),
	is_third_party: field("is_third_party", "Third party", "Check"),
	third_party_supplier: link("third_party_supplier", "Third party supplier", "Supplier"),
	inspection_type: field("inspection_type", "Inspection Type", "Select", { options: "\nPre-FInal\nFinal\nRe-Final", reqd: 1 }),
	unit_name: link("unit_name", "Unit Name", "Supplier"),
	posting_date: field("posting_date", "Posting Date", "Date", readonly),
	description: field("description", "Description", "Data"),
	offer_qty: field("offer_qty", "Offer Qty", "Int"),
	checking_level: field("checking_level", "Checking Level", "Select", { options: "\nLevel 1\nLevel 2", reqd: 1 }),
	major_aql_level: link("major_aql_level", "Major AQL Level", "SD YRP AQL Level"),
	minor_aql_level: link("minor_aql_level", "Minor AQL Level", "SD YRP AQL Level"),
	sample_piece_count: field("sample_piece_count", "AQL Sample", "Int", readonly),
	major_defect_maximum_allowed: field("major_defect_maximum_allowed", "Allowed Major", "Int", readonly),
	minor_defect_maximum_allowed: field("minor_defect_maximum_allowed", "Allowed Minor", "Int", readonly),
	major_defect_found: field("major_defect_found", "Found Major", "Int"),
	minor_defect_found: field("minor_defect_found", "Found Minor", "Int"),
	spi_found: field("spi_found", "SPI Found", "Int"),
	result: field("result", "Result", "Select", { options: "\nPass\nFail\nHold" }),
	calculated_result: field("calculated_result", "Calculated Result", "Data", readonly),
	inspector: link("inspector", "Inspector", "User", readonly),
	measurement_deviation: field("measurement_deviation", "Measurement Deviation", "Small Text"),
	remarks_and_suggestions: field("remarks_and_suggestions", "Remarks and Suggestions", "Small Text"),
}

export const INSPECTION_GROUPS = [
	{ key: "work_order", label: "Work Order", fields: ["against_id", "item", "lot", "supplier", "order_qty"] },
	{ key: "third_party", label: "Third party", fields: ["is_third_party", "third_party_supplier"] },
	{ key: "inspection", label: "Inspection", fields: ["inspection_type", "unit_name", "posting_date", "description"] },
	{ key: "selection", label: "Colours & Sizes", fields: [] },
	{ key: "quantities", label: "Quantities & AQL", fields: ["offer_qty", "checking_level", "major_aql_level", "minor_aql_level", "sample_piece_count", "major_defect_maximum_allowed", "minor_defect_maximum_allowed"] },
	{ key: "defects", label: "Defects", fields: ["major_defect_found", "minor_defect_found", "spi_found", "result"] },
	{ key: "notes", label: "Notes", fields: ["measurement_deviation", "remarks_and_suggestions"] },
	{ key: "approval", label: "Approval sheet", fields: [] },
]

export function visibleInspectionFields(group, values, view = false) {
	const names = group.fields.filter((key) => key !== "third_party_supplier" || Number(values.is_third_party))
	if (view && group.key === "defects") names.push("calculated_result", "inspector")
	return names.map((key) => ({
		...INSPECTION_FIELDS[key],
		reqd: key === "third_party_supplier" ? Number(values.is_third_party) === 1 : INSPECTION_FIELDS[key].reqd,
	}))
}
