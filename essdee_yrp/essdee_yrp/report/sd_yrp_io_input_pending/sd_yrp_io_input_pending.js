frappe.query_reports["SD YRP IO Input Pending"] = {
	filters: [
		{fieldname: "supplier", label: __("Warehouse"), fieldtype: "Link", options: "Supplier", reqd: 1},
		{fieldname: "work_station", label: __("Work Station"), fieldtype: "Data"},
		{fieldname: "search", label: __("Search lot or item"), fieldtype: "Data"},
	],
};
