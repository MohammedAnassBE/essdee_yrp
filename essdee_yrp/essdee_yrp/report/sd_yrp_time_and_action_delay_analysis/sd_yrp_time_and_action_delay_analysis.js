// Copyright (c) 2024, Essdee and contributors
// For license information, please see license.txt

frappe.query_reports["SD YRP Time and Action Delay Analysis"] = {
	"filters": [
		{
			"fieldname": "lot",
			"fieldtype": "Link",
			"options": "SD YRP Lot",
			"label": "Lot",
			"reqd": true,
		},
		{
			"fieldname": "time_and_action",
			"fieldtype": "Link",
			"label": "Time and Action",
			"options": "SD YRP Time and Action",
			"reqd": true,
			"get_query":function(){
				return {
					filters: {
						"lot":frappe.query_report.get_filter_value("lot")
					}
				}
			}

		}
	]
};
