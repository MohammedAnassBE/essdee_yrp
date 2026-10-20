frappe.query_reports["SD YRP Finishing Plan Dispatch Details"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.month_start() },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{
			fieldname: "lots", label: __("Lot"), fieldtype: "MultiSelectList", options: "SD YRP Lot",
			get_data(txt) { return frappe.db.get_link_options("SD YRP Lot", txt); },
		},
		{
			fieldname: "items", label: __("Item"), fieldtype: "MultiSelectList", options: "Item",
			get_data(txt) { return frappe.db.get_link_options("Item", txt, { has_variants: 1 }); },
		},
	],
};
