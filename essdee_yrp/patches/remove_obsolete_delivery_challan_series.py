import frappe


OBSOLETE_PROPERTY_SETTERS = (
	"Delivery Challan-naming_series-default",
	"Delivery Challan-naming_series-options",
)


def execute():
	"""Remove Essdee overrides after Delivery Challan series returned to base YRP."""
	frappe.db.delete("Property Setter", {"name": ["in", OBSOLETE_PROPERTY_SETTERS]})
	frappe.clear_cache(doctype="Delivery Challan")
