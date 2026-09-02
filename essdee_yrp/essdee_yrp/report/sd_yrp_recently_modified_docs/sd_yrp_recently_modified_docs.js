frappe.query_reports["SD YRP Recently Modified Docs"] = {
	filters: [
		{
			fieldname: "doctype",
			label: __("DocType"),
			fieldtype: "Link",
			options: "DocType",
			default: "DocType",
			reqd: 1,
		},
		{
			fieldname: "days",
			label: __("Days"),
			fieldtype: "Int",
			default: 7,
			reqd: 1,
		},
	],
};
