// Copyright (c) 2024, Essdee and contributors
// For license information, please see license.txt

frappe.query_reports["SD YRP Time and Action Summary"] = {
	"filters": [
		{
			"fieldtype":"Link",
			"fieldname":"lot",
			"label":"Lot",
			"options":"SD YRP Lot",
		}

	]
};
