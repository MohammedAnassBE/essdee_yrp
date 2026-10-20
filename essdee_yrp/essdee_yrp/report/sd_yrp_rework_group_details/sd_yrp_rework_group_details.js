frappe.query_reports["SD YRP Rework Group Details"] = {
	filters: [
		{ fieldname: "lot", label: __("Lot"), fieldtype: "Link", options: "SD YRP Lot" },
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "colour", label: __("Colour"), fieldtype: "Data" },
		{ fieldname: "show_reworked", label: __("Show Reworked"), fieldtype: "Check", default: 0 },
	],
};
