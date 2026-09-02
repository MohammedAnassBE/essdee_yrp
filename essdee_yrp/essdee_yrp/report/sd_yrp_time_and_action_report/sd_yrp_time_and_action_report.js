// Copyright (c) 2024, Essdee and contributors
// For license information, please see license.txt

frappe.query_reports["SD YRP Time and Action Report"] = {
	"filters": [
		{
			"fieldtype":"Link",
			"fieldname":"lot",
			"options":"SD YRP Lot",
			"label":"Lot"
		}
	]
};
