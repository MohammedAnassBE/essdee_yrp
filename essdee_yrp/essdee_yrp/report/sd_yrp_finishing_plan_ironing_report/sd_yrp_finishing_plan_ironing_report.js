frappe.query_reports["SD YRP Finishing Plan Ironing Report"] = {
	filters: [
		{
			fieldname: "summary", label: __("Summary"), fieldtype: "Check", default: 0,
			on_change(report) {
				const summary = Boolean(report.get_filter_value("summary"));
				for (const fieldname of ["date", "from_date", "to_date"]) {
					const filter = report.get_filter(fieldname);
					filter.df.reqd = Number(fieldname === "date" ? !summary : summary);
					filter.refresh();
				}
				report.refresh();
			},
		},
		{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1, depends_on: "eval:!doc.summary" },
		{
			fieldname: "items", label: __("Item"), fieldtype: "MultiSelectList", options: "Item", depends_on: "eval:doc.summary",
			get_data(txt) { return frappe.db.get_link_options("Item", txt, { has_variants: 1 }); },
		},
		{
			fieldname: "lots", label: __("Lot"), fieldtype: "MultiSelectList", options: "SD YRP Lot", depends_on: "eval:doc.summary",
			get_data(txt) { return frappe.db.get_link_options("SD YRP Lot", txt); },
		},
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 0, depends_on: "eval:doc.summary" },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 0, depends_on: "eval:doc.summary" },
	],
};
