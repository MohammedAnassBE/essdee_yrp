frappe.query_reports["SD YRP Supplier Pending Report"] = {
	filters: [
		{
			fieldname: "supplier",
			label: __("Supplier"),
			fieldtype: "Link",
			options: "Supplier",
			reqd: 1,
		},
		{
			fieldname: "process",
			label: __("Process"),
			fieldtype: "Link",
			options: "YRP Process",
			reqd: 1,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		let formatted = default_formatter(value, row, column, data);
		if (!data) return formatted;
		let colour = data.is_total ? "var(--subtle-fg)" : "";
		if (data.type === "Difference" && (column.fieldname.startsWith("size_") || column.fieldname === "total")) {
			colour = Number(value) < 0 ? "var(--red-100)" : Number(value) > 0 ? "var(--green-100)" : "var(--yellow-100)";
		}
		if (colour) formatted = `<span style="display:block;background:${colour};font-weight:${data.is_total ? 600 : 400}">${formatted}</span>`;
		return formatted;
	},
};
