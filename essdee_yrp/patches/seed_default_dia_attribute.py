import frappe


def execute():
	"""Keep the fabric dia attribute that used to be hard-coded as "Dia"; never overwrite."""
	settings = "SD YRP IPD Settings"
	if not frappe.db.get_single_value(settings, "default_dia_attribute") and frappe.db.exists(
		"Item Attribute", "Dia"
	):
		frappe.db.set_single_value(settings, "default_dia_attribute", "Dia")
