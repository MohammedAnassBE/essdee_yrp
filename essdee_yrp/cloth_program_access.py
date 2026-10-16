import frappe
from frappe import _


def has_cloth_program_role():
	roles = frappe.get_roles()
	if "System Manager" in roles:
		return True
	merch_role = frappe.db.get_single_value("SD YRP MRP Settings", "merch_user_role")
	return bool(merch_role and merch_role in roles)


def require_cloth_program_role():
	if has_cloth_program_role():
		return
	if not frappe.db.get_single_value("SD YRP MRP Settings", "merch_user_role"):
		frappe.throw(_("Set Merch User Role in SD YRP MRP Settings."), frappe.PermissionError)
	frappe.throw(
		_("Only System Managers or users with the Merch User Role can manage Cloth Programs."),
		frappe.PermissionError,
	)
