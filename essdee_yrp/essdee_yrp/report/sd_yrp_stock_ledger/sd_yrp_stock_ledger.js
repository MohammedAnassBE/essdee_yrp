

frappe.query_reports["SD YRP Stock Ledger"] = {
	"filters": [
		{
			"fieldname":"from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			"reqd": 1
		},
		{
			"fieldname":"to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"reqd": 1
		},
		{
			"fieldname":"warehouse",
			"label": __("Warehouse"),
			"fieldtype": "Link",
			"options": "Supplier",
		},
		{
			"fieldname":"item",
			"label": __("Item Variant"),
			"fieldtype": "Link",
			"options": "Item",
			get_query: () => ({filters: {variant_of: ["is", "set"]}}),
		},
		{
			"fieldname":"parent_item",
			"label": __("Item"),
			"fieldtype": "Link",
			"options": "Item",
			get_query: () => ({filters: {variant_of: ["is", "not set"]}}),
		},
		{
			"fieldname":"lot",
			"label": __("Lot"),
			"fieldtype": "Link",
			"options": "SD YRP Lot"
		},
		{
			"fieldname":"received_type",
			"label": __("Received Type"),
			"fieldtype": "Link",
			"options": "YRP Received Type"
		},
		{
			"fieldname":"brand",
			"label": __("Brand"),
			"fieldtype": "Link",
			"options": "Brand"
		},
		{
			"fieldname":"voucher_no",
			"label": __("Voucher #"),
			"fieldtype": "Data"
		},
	],
	"formatter": function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname == "out_qty" && data && data.out_qty < 0) {
			value = "<span style='color:red'>" + value + "</span>";
		} else if (column.fieldname == "in_qty" && data && data.in_qty > 0) {
			value = "<span style='color:green'>" + value + "</span>";
		} else if (column.fieldname == "warehouse_name") {
			value = `<a href="/app/supplier/${data.warehouse}" data-doctype="Supplier" data-name="${data.warehouse}" data-value="${data.warehouse}">${data.warehouse_name}</a>`;
		}
		return value;
	},
};
