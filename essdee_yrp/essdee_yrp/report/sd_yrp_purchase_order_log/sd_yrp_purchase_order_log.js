// Copyright (c) 2024, Essdee and contributors
// For license information, please see license.txt


frappe.query_reports["SD YRP Purchase Order Log"] = {
	"filters": [
		{
            "fieldname": "purchase_order",
            "label": "Purchase Order",
            "fieldtype": "Link",
            "options": "YRP Purchase Order",
            "width": 100,
        },
		{
            "fieldname": "po_date",
            "label": "PO Date",
            "fieldtype": "Date",
            "width": 150,
        },
		{
            "fieldname": "supplier",
            "label": "Supplier",
            "fieldtype": "Link",
            "options": "YRP Supplier",
            "width": 200,
        },
	]
};
