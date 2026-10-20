

frappe.query_reports["SD YRP Lot Profit Comparison"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"reqd": 1,
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -3),
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"reqd": 1,
			"default": frappe.datetime.get_today(),
		},
		{
			"fieldname": "lot",
			"label": __("Lot"),
			"fieldtype": "Link",
			"options": "SD YRP Lot",
		},
		{
			"fieldname": "item",
			"label": __("Item"),
			"fieldtype": "Link",
			"options": "SD YRP FG Item Master",
		},
	],
	formatter: function(value, row, column, data, default_formatter) {
		let formatted_value = default_formatter(value, row, column, data);

		if (column.fieldname.includes("_qty") || column.fieldname.includes("_profit")) {
			if (!value) {
				return ""
			} else {
				if (column.fieldname.includes("_qty")) {
					let name = data[column.fieldname.replace("_qty", "_name")];
					formatted_value = '<a href="/app/sd-yrp-lotwise-item-profit/' + name + '">' + formatted_value + '</a>';
				}
			}
		}


		return formatted_value;
	}
};
