frappe.query_reports["SD YRP PPO Report"] = {
	filters: [
		{
			fieldname: "status", label: __("Status"), fieldtype: "Select",
			options: "\nDraft\nPPO Request\nOpen\nPending Request\nItem Changed\nNot Processed\nClose Request\nClosed",
		},
		{ fieldname: "product_category", label: __("Product Category"), fieldtype: "Link", options: "SD YRP Product Category" },
		{
			fieldname: "item", label: __("Item"), fieldtype: "MultiSelectList",
			get_data(txt) { return frappe.db.get_link_options("Item", txt, { has_variants: 1 }); },
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date" },
		{ fieldname: "show_fabric", label: __("Show Fabric"), fieldtype: "Check", default: 0 },
		{ fieldname: "show_dia", label: __("Show Dia"), fieldtype: "Check", default: 0 },
		{ fieldname: "show_gsm", label: __("Show GSM"), fieldtype: "Check", default: 0 },
		{ fieldname: "summarized", label: __("Summarized"), fieldtype: "Check", default: 0 },
	],
};
