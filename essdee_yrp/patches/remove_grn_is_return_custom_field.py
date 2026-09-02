import frappe


CUSTOM_FIELD = "Goods Received Note-is_return"


def execute():
	"""Remove the obsolete Essdee field now provided by base YRP."""
	frappe.db.delete("Custom Field", {"name": CUSTOM_FIELD})
	frappe.clear_cache(doctype='YRP Goods Received Note')
