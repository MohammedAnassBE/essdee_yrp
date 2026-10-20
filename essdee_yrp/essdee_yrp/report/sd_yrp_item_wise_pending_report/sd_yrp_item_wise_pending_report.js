frappe.query_reports["SD YRP Item Wise Pending Report"] = {
	filters: [
		{
			fieldname: "warehouse", label: __("Warehouse"), fieldtype: "MultiSelectList",
			get_data: (txt) => frappe.db.get_link_options("Warehouse", txt, {disabled: 0, is_group: 0}),
		},
		{fieldname: "search", label: __("Start typing to filter"), fieldtype: "Data"},
	],
};
