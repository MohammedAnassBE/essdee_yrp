frappe.query_reports["SD YRP Datewise Item Packed"] = {
	filters: [
		{fieldname: "start_date", label: __("Start Date"), fieldtype: "Date", reqd: 1},
		{fieldname: "end_date", label: __("End Date"), fieldtype: "Date", reqd: 1},
		{fieldname: "sales_partner", label: __("Customer Sales Partner (Current)"), fieldtype: "Link", options: "Sales Partner"},
		{fieldname: "customer", label: __("Customer"), fieldtype: "Link", options: "Customer"},
		{fieldname: "search", label: __("Start typing to filter"), fieldtype: "Data"},
	],
};
