frappe.query_reports["SD YRP Rework Completion Report"] = {
	filters: [
		{ fieldname: "lot", label: __("Lot"), fieldtype: "Link", options: "SD YRP Lot", reqd: 1 },
		{ fieldname: "process", label: __("Process"), fieldtype: "Link", options: "YRP Process", reqd: 1 },
	],
};
