import frappe

ROLE_DEFAULTS = {
	("SD YRP MRP Settings", "production_planner_role"): "Production Planner",
	("SD YRP T and A Settings", "t_and_a_admin_role"): "T & A Admin",
}


def execute():
	"""Seed role settings with the roles that used to be hard-coded; never overwrite."""
	for (doctype, fieldname), role in ROLE_DEFAULTS.items():
		if not frappe.db.get_single_value(doctype, fieldname) and frappe.db.exists("Role", role):
			frappe.db.set_single_value(doctype, fieldname, role)
