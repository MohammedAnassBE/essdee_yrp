import frappe
from frappe.permissions import add_permission

ACCOUNTS_REPORT_ROLE = "Accounts User"
ACCOUNTS_REPORT_GRANTS = {
	"YRP Stock Ledger Entry": {0: ("read", "report")},
	"SD YRP Cutting LaySheet": {0: ("read",)},
	"SD YRP Cutting Plan": {0: ("read",), 1: ("read",)},
	"SD YRP Cutting Order": {0: ("read",)},
	"YRP Work Order": {0: ("read",)},
	"SD YRP Sewing Plan": {0: ("read", "report")},
	"SD YRP Sewing Plan Entry Detail": {0: ("read",)},
	"SD YRP Finishing Plan": {0: ("read",)},
	"YRP Goods Received Note": {0: ("read",)},
	"YRP Delivery Challan": {0: ("read",)},
}
STOCK_BALANCE_REPORT = "YRP Stock Balance"
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


def execute(*, allow_missing_report=False):
	"""Grant Accounts User only the read/report access used by Accounts reports."""
	for doctype, grants_by_level in ACCOUNTS_REPORT_GRANTS.items():
		for permlevel, permission_types in grants_by_level.items():
			_grant_permissions(doctype, permlevel, permission_types)
	_add_stock_balance_report_role(allow_missing_report)


def _grant_permissions(doctype, permlevel, permission_types):
	filters = {
		"parent": doctype,
		"role": ACCOUNTS_REPORT_ROLE,
		"permlevel": permlevel,
		"if_owner": 0,
	}
	permission = frappe.db.get_value(
		"Custom DocPerm",
		filters,
		["name", *permission_types],
		as_dict=True,
	)
	if not permission:
		permission_name = add_permission(doctype, ACCOUNTS_REPORT_ROLE, permlevel)
		if permission_name:
			values = {
				permission_type: int(permission_type in permission_types)
				for permission_type in PERMISSION_FIELDS
			}
		else:
			permission_name = frappe.db.get_value("Custom DocPerm", filters, "name")
			values = {permission_type: 1 for permission_type in permission_types}
	else:
		permission_name = permission.name
		values = {
			permission_type: 1
			for permission_type in permission_types
			if not permission.get(permission_type)
		}
	if not permission_name:
		frappe.throw(f"Could not create an unrestricted Accounts User permission for {doctype}")
	if values:
		frappe.db.set_value("Custom DocPerm", permission_name, values)
		frappe.clear_cache(doctype=doctype)


def _add_stock_balance_report_role(allow_missing_report):
	if allow_missing_report and not frappe.db.exists("Report", STOCK_BALANCE_REPORT):
		return
	report = frappe.get_doc("Report", STOCK_BALANCE_REPORT)
	custom_role_name = frappe.db.get_value("Custom Role", {"report": report.name}, "name")
	if custom_role_name:
		custom_role = frappe.get_doc("Custom Role", custom_role_name)
		if any(row.role == ACCOUNTS_REPORT_ROLE for row in custom_role.roles):
			return
		custom_role.append("roles", {"role": ACCOUNTS_REPORT_ROLE})
		custom_role.save(ignore_permissions=True)
	else:
		roles = [row.role for row in report.roles if row.role]
		if ACCOUNTS_REPORT_ROLE not in roles:
			roles.append(ACCOUNTS_REPORT_ROLE)
		frappe.get_doc({
			"doctype": "Custom Role",
			"report": report.name,
			"ref_doctype": report.ref_doctype,
			"roles": [{"role": role} for role in roles],
		}).insert(ignore_permissions=True)
	frappe.clear_cache(doctype="Report")
