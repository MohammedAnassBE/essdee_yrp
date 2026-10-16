import frappe
from frappe.permissions import (
	add_permission,
	setup_custom_perms,
	update_permission_property,
)

PERMISSION_FIELDS = (
	"select",
	"read",
	"write",
	"create",
	"delete",
	"submit",
	"cancel",
	"amend",
	"print",
	"email",
	"report",
	"import",
	"export",
	"share",
	"mask",
)
PERMISSION_GRANTS = {
	"Item": {
		"Purchase Manager": ("read", "create", "write"),
	},
	"YRP Item Item Attribute Mapping": {
		"Purchase Manager": ("read", "create", "write"),
		"Item Manager": ("read", "create", "write"),
	},
	"YRP Item Attribute Value": {
		"Purchase Manager": ("read", "create"),
		"Item Manager": ("read", "create"),
	},
	"Item Attribute": {
		"Purchase Manager": ("read", "select"),
		"Item Manager": ("read", "select"),
	},
}


def execute():
	grant_permissions(PERMISSION_GRANTS)


def grant_permissions(grants, permlevel=0):
	for doctype, role_grants in grants.items():
		setup_custom_perms(doctype)
		for role, permission_types in role_grants.items():
			_grant_permissions(doctype, role, permission_types, permlevel)
		frappe.clear_cache(doctype=doctype)


def _grant_permissions(doctype, role, permission_types, permlevel=0):
	filters = {
		"parent": doctype,
		"role": role,
		"permlevel": permlevel,
		"if_owner": 0,
	}
	permission_name = frappe.db.get_value("Custom DocPerm", filters, "name")
	created = not permission_name
	if created:
		permission_name = add_permission(doctype, role, permlevel, permission_types[0])
	if not permission_name:
		frappe.throw(f"Could not create an unrestricted {role} permission for {doctype}")

	same_level_count = frappe.db.count(
		"Custom DocPerm",
		{"parent": doctype, "role": role, "permlevel": permlevel},
	)
	for permission_type in permission_types:
		if same_level_count == 1:
			update_permission_property(
				doctype,
				role,
				permlevel,
				permission_type,
				1,
				if_owner=0,
			)
		elif not frappe.db.get_value("Custom DocPerm", permission_name, permission_type):
			# Frappe's helper ignores if_owner when multiple same-level rows exist.
			frappe.db.set_value("Custom DocPerm", permission_name, permission_type, 1)

	if created:
		# New Custom DocPerm rows default export=1; grant exactly the requested rights.
		frappe.db.set_value(
			"Custom DocPerm",
			permission_name,
			{
				permission_type: int(permission_type in permission_types)
				for permission_type in PERMISSION_FIELDS
			},
		)
