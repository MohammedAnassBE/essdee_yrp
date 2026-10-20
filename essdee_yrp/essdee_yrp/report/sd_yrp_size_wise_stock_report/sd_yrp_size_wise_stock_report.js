frappe.query_reports["SD YRP Size Wise Stock Report"] = {
	filters: [
		{
			fieldname: "lot", label: __("Lots"), fieldtype: "MultiSelectList",
			get_data(txt) { return frappe.db.get_link_options("SD YRP Lot", txt); },
		},
		{
			fieldname: "item", label: __("Items"), fieldtype: "MultiSelectList",
			get_data(txt) { return frappe.db.get_link_options("Item", txt, { has_variants: 1 }); },
		},
		{ fieldname: "product_category", label: __("Product Category"), fieldtype: "Link", options: "SD YRP Product Category" },
		{ fieldname: "lot_status", label: __("Lot Status"), fieldtype: "Select", options: "Open\nClosed", default: "Open" },
		{
			fieldname: "process_list", label: __("Processes (in order)"), fieldtype: "MultiSelectList",
			description: __("Select processes in comparison order. Remove and select again to reorder."),
			get_data(txt) { return frappe.db.get_link_options("YRP Process", txt); },
		},
	],
};
