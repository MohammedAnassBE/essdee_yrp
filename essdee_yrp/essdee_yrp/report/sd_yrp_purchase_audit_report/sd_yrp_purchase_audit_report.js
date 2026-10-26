const ITEM_QUERY =
	"essdee_yrp.essdee_yrp.report.sd_yrp_purchase_audit_report.sd_yrp_purchase_audit_report.item_query";

const get_item_filters = () => ({
	item_group: frappe.query_report.get_filter_value("item_group") || [],
});

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
			get_data: (txt) =>
				frappe.xcall("frappe.desk.search.search_link", {
					doctype: "Item",
					txt,
					query: ITEM_QUERY,
					filters: get_item_filters(),
				}),
		},
		{
			fieldname: "item_variant",
			label: __("Item Variant"),
			fieldtype: "Link",
			options: "Item",
			get_query: () => ({ query: ITEM_QUERY, filters: { ...get_item_filters(), variant: 1 } }),
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "MultiSelectList",
			options: "Item Group",
			get_data: (txt) => frappe.db.get_link_options("Item Group", txt),
			on_change: (report) => {
				if (report.get_filter_value("item")?.length || report.get_filter_value("item_variant")) {
					report.set_filter_value({ item: [], item_variant: "" });
				} else {
					report.refresh();
				}
			},
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
