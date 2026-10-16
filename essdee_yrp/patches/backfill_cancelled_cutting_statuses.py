import frappe


def execute():
	for doctype, fieldname in (
		("SD YRP Cutting Order", "co_status"),
		("SD YRP Cutting Plan", "cp_status"),
	):
		frappe.db.set_value(doctype, {"docstatus": 2}, fieldname, "Cancelled", update_modified=False)
