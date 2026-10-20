frappe.query_reports["SD YRP Rejection Details"] = {
	filters: [
		{ fieldname: "start_date", label: __("Start Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.add_months(frappe.datetime.month_start(), -1) },
		{ fieldname: "end_date", label: __("End Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.add_days(frappe.datetime.month_start(), -1) },
		{ fieldname: "lot", label: __("Lot"), fieldtype: "Link", options: "SD YRP Lot" },
		{ fieldname: "item", label: __("Item"), fieldtype: "Link", options: "Item" },
		{ fieldname: "colour", label: __("Colour"), fieldtype: "Data" },
	],
};
