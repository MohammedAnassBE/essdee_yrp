"""Restore mapped MRP report permissions on shared YRP doctypes."""

import frappe
from frappe.permissions import add_permission

ITEM_BALANCE_FIELDS = ("read", "report", "select", "export", "print", "email", "share")
REPORT_FIELDS = ("read", "report")
# Reference DocType -> (report roles without a standard grant, granted permission fields).
REPORT_REFERENCE_GRANTS = {
	"YRP Bin": (("Merch Manager", "Merch User"), ITEM_BALANCE_FIELDS),
	"YRP Stock Reservation Entry": (("Merch Manager", "Merch User"), REPORT_FIELDS),
	"YRP Stock Ledger Entry": (("Accounts Manager", "Merch Manager", "Merch User"), REPORT_FIELDS),
}


def ensure_report_permissions():
	"""Give report roles the reference DocType read and report access Frappe checks on run."""
	for doctype, (roles, fields) in REPORT_REFERENCE_GRANTS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		for role in roles:
			filters = {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
			name = frappe.db.get_value("Custom DocPerm", filters, "name")
			if not name:
				# Frappe copies standard rows before the first custom grant.
				name = add_permission(doctype, role)
			frappe.db.set_value("Custom DocPerm", name, {field: 1 for field in fields})
		frappe.clear_cache(doctype=doctype)
