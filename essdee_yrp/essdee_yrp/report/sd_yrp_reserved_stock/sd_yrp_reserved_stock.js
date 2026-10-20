
frappe.query_reports["SD YRP Reserved Stock"] = {
	filters: [
		{
			fieldname: "brand",
			label: __("Brand"),
			fieldtype: "Link",
			options: "Brand",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
			get_query: () => ({
				filters: {
					is_stock_item: 1,
					variant_of: ["is", "not set"],
					brand : frappe.query_report.get_filter_value("brand"),
				},
			}),
		},
		{
			fieldname : "item_code",
			label : __("Item Code"),
			fieldtype : "Link",
			options : "Item",
			get_query: () => ({
				filters: {
					variant_of : frappe.query_report.get_filter_value("item")? frappe.query_report.get_filter_value("item") : ["is", "set"],
				}
			}),
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname : "lot",
			label : __("Lot"),
			fieldtype : "Link",
			options : "SD YRP Lot",

		},
		{
			fieldname : "received_type",
			label : __("Received Type"),
			fieldtype : "Link",
			options : "YRP Received Type",
		},
		{
			fieldname: "stock_reservation_entry",
			label: __("Stock Reservation Entry"),
			fieldtype: "Link",
			options: "YRP Stock Reservation Entry",
			get_query: () => ({
				filters: {
					docstatus: 1,
				},
			}),
		},
		{
			fieldname: "voucher_type",
			label: __("Voucher Type"),
			fieldtype: "Select",
			options: "\nPacking Slip",
			default: "Packing Slip",

		},
		{
			fieldname: "voucher_no",
			label: __("Voucher No"),
			fieldtype: "Data",

		},
	],
	formatter: (value, row, column, data, default_formatter) => {
		value = default_formatter(value, row, column, data);

		if (data) {
			if (column.fieldname == "status") {
				switch (data.status) {
					case "Partially Reserved":
						value = "<span style='color:orange'>" + value + "</span>";
						break;
					case "Reserved":
						value = "<span style='color:blue'>" + value + "</span>";
						break;
					case "Partially Delivered":
						value = "<span style='color:purple'>" + value + "</span>";
						break;
					case "Delivered":
						value = "<span style='color:green'>" + value + "</span>";
						break;
				}
			} else if (column.fieldname == "delivered_qty") {
				if (data.delivered_qty > 0) {
					if (data.reserved_qty > data.delivered_qty) {
						value = "<span style='color:blue'>" + value + "</span>";
					} else {
						value = "<span style='color:green'>" + value + "</span>";
					}
				} else {
					value = "<span style='color:red'>" + value + "</span>";
				}
			}
		}

		return value;
	},
};
