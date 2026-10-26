frappe.query_reports["SD YRP Purchase Audit Report"] = {
	filters: [
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
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
			on_change: (report) => {
				if (report.get_filter_value("warehouse")) {
					report.set_filter_value("warehouse", "");
				} else {
					report.refresh();
				}
			},
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: () => {
				const supplier = frappe.query_report.get_filter_value("supplier");
				return supplier ? { filters: { supplier } } : {};
			},
		},
		{
			fieldname: "item",
			label: __("Item"),
			fieldtype: "MultiSelectList",
			options: "Item",
			get_data: (txt) => frappe.db.get_link_options("Item", txt, { variant_of: ["is", "not set"] }),
		},
		{
			fieldname: "item_variant",
			label: __("Item Variant"),
			fieldtype: "Link",
			options: "Item",
			get_query: () => ({ filters: { has_variants: 0 } }),
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "MultiSelectList",
			options: "Item Group",
			get_data: (txt) => frappe.db.get_link_options("Item Group", txt),
		},
		{
			fieldname: "received_type",
			label: __("Received Type"),
			fieldtype: "Link",
			options: "YRP Received Type",
		},
		{
			fieldname: "lot",
			label: __("Lot"),
			fieldtype: "Link",
			options: "SD YRP Lot",
		},
		{
			fieldname: "summarized_view",
			label: __("Summarized View"),
			fieldtype: "Check",
			on_change: (report) => {
				const is_summarized = report.get_filter_value("summarized_view");
				if (!is_summarized && report.get_filter_value("month_wise_report")) {
					report.set_filter_value("month_wise_report", 0);
				} else {
					report.refresh();
				}
			},
		},
		{
			fieldname: "month_wise_report",
			label: __("Month-wise Report"),
			fieldtype: "Check",
			depends_on: "eval:doc.summarized_view",
		},
	],
};
