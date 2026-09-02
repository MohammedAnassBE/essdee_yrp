// Copyright (c) 2026, Essdee and contributors
// For license information, please see license.txt

frappe.query_reports["SD YRP Non Jobwork Issued Items"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"fieldtype": "Date",
			"label": __("From Date"),
			"default": frappe.datetime.add_months(frappe.datetime.nowdate(), -1),
			"reqd": 1
		},
		{
			"fieldname": "to_date",
			"fieldtype": "Date",
			"label": __("To Date"),
			"default": frappe.datetime.nowdate(),
			"reqd": 1
		},
		{
			"fieldname": "purpose",
			"fieldtype": "Select",
			"label": __("Purpose"),
			"options": "\nMaterial Issue\nSend to Warehouse"
		},
		{
			"fieldname": "lot",
			"fieldtype": "Link",
			"options": "SD YRP Lot",
			"label": __("Lot")
		},
		{
			"fieldname": "from_location",
			"fieldtype": "Link",
			"options": "YRP Warehouse",
			"label": __("From Location")
		},
		{
			"fieldname": "supplier",
			"fieldtype": "Link",
			"options": "YRP Supplier",
			"label": __("Supplier")
		},
		{
			"fieldname": "item",
			"fieldtype": "Link",
			"options": "YRP Item",
			"label": __("Item")
		}
	]
};
