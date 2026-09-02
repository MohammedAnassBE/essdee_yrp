import frappe


def execute():
	if not frappe.db.exists("DocType", "IPD Consumption"):
		return
	if frappe.db.exists("DocType", 'SD YRP IPD Compacting'):
		return

	frappe.rename_doc(
		"DocType",
		"IPD Consumption",
		'SD YRP IPD Compacting',
		force=True,
	)
