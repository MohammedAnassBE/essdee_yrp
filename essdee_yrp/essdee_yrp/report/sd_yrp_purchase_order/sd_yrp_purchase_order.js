frappe.query_reports["SD YRP PURCHASE ORDER"] = {
	filters: [
		{ fieldname: "open_status", label: __("Open Status"), fieldtype: "Select", options: "\nOpen\nClosed", default: "Open" },
		{ fieldname: "supplier", label: __("Supplier"), fieldtype: "Link", options: "Supplier" },
		{ fieldname: "name", label: __("ID"), fieldtype: "Link", options: "Purchase Order" },
		{ fieldname: "po_date", label: __("PO Date"), fieldtype: "Date" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nDraft\nPending Approval\nOrdered\nPartially Delivered\nDelivered\nCancelled\nPartially Cancelled\nOverdue\nClosed" },
		{ fieldname: "docstatus", label: __("Document Status"), fieldtype: "Select", options: [
			{ label: "", value: "" }, { label: __("Draft"), value: "0" },
			{ label: __("Submitted"), value: "1" }, { label: __("Cancelled"), value: "2" },
		] },
	],
};
