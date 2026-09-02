// Copyright (c) 2025, Essdee and contributors
// For license information, please see license.txt

frappe.query_reports["SD YRP GRN Report"] = {
	"filters": [
		{
			fieldname: 'from_date',
			fieldtype: "Date",
			label: "From Date",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.nowdate(), -1),
		},
		{
			fieldname: 'to_date',
			fieldtype: "Date",
			label: "To Date",
			reqd: 1,
			default: frappe.datetime.nowdate(),
		},
		{
			fieldname: "lot",
			fieldtype: "Link",
			options: "SD YRP Lot",
			label: "Lot",
		},
		{
			fieldname: "supplier",
			fieldtype: "Link",
			options: "YRP Supplier",
			label: "Supplier",
		},
		{
			fieldname: "delivery_location",
			fieldtype: "Link",
			options: "YRP Supplier",
			label: "Delivery Location",
		},
	]
};
