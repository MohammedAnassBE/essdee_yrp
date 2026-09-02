// Copyright (c) 2025, Essdee and contributors
// For license information, please see license.txt

frappe.query_reports["SD YRP Cut Bundle Balance"] = {
	"filters": [
		{
			"fieldname": "lot",
			"fieldtype": "Link",
			"options": "SD YRP Lot",
			"label": "Lot",
		},
		{
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "YRP Supplier",
			"label": "Supplier",
		}
	]
};
