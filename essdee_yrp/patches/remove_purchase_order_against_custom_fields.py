import frappe

CUSTOM_FIELDS = ("Purchase Order-against", "Purchase Order-against_id")


def execute():
	"""Drop Against / Against ID; the Production Orders table replaces them."""
	frappe.db.delete("Custom Field", {"name": ["in", CUSTOM_FIELDS]})
	frappe.clear_cache(doctype="Purchase Order")
