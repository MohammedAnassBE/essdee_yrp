import frappe
from frappe.permissions import add_permission, setup_custom_perms

READ = ("read",)
VIEW = ("read", "print", "email", "report", "export", "share")
ENTRY = (*VIEW, "write", "create")
STORE_ENTRY = (*ENTRY, "submit")
STORE_MANAGER_ENTRY = (*STORE_ENTRY, "cancel")
FINISHING_DC = (*STORE_MANAGER_ENTRY, "delete", "amend")
QA_VIEW = ("read", "print", "report")
# Frappe allows Cancel only on a row that also has Submit and Write.
QA_CANCEL = (*QA_VIEW, "write", "submit", "cancel")

# Production MRP floor-role grants that YRP's own DocType permissions do not carry.
MRP_ROLE_GRANTS = {
	"YRP Delivery Challan": {
		"Store User": STORE_ENTRY,
		"Store Manager": STORE_ENTRY,
		"Finishing User": FINISHING_DC,
		"Production Planner": STORE_MANAGER_ENTRY,
	},
	"YRP Goods Received Note": {
		"Store User": STORE_ENTRY,
		"Store Manager": STORE_ENTRY,
		"Finishing User": STORE_MANAGER_ENTRY,
	},
	"YRP Debit": {
		"Brand QA User": STORE_ENTRY,
		"Brand QA Manager": QA_CANCEL,
		"Merch Manager": (*STORE_MANAGER_ENTRY, "amend"),
	},
	"YRP Item Production Detail": {"All": READ},
	"YRP Process Cost": {
		"Merch User": ENTRY,
		"Merch Manager": (*STORE_MANAGER_ENTRY, "delete"),
		"Production Planner": VIEW,
		"Brand QA Manager": VIEW,
		"Brand QA User": QA_VIEW,
	},
	"YRP Purchase Invoice": {"Merch User": (*ENTRY, "delete"), "Brand QA Manager": VIEW},
	# Not a production row: Purchase users reached it there through Stock/Accounts User.
	"YRP Excel Sticker Print": {"Purchase User": ("read", "write", "create", "submit", "print")},
	# Quality department cards that open Planning, PD and Merch pages read-only.
	**{
		doctype: {"Brand QA User": QA_VIEW, "Brand QA Manager": QA_VIEW}
		for doctype in (
			"SD YRP Cutting Plan",
			"SD YRP Lot",
			"SD YRP Sewing Plan",
			"SD YRP Finishing Plan",
			"SD YRP Product",
			"SD YRP Product Release",
			"SD YRP Lotwise Item Profit",
			"Item",
		)
	},
	# Planning's Stock Transfers section.
	**{
		doctype: {"Production Planner": STORE_ENTRY}
		for doctype in ("YRP Stock Entry", "YRP Stock Reconciliation", "SD YRP Lot Transfer")
	},
	# Attribute values back link fields on every department's forms.
	"YRP Item Attribute Value": {"All": ("read", "select")},
}
# YRP grants these roles access production never gave them.
MRP_ROLE_REVOKES = {
	"YRP Process Cost": ("Purchase User", "Purchase Manager"),
	"YRP Purchase Invoice": ("Purchase User", "Purchase Manager"),
	"YRP Debit": ("Purchase Manager", "Stock Manager"),
}
# Production runs the Process Cost workflow with Merch roles; YRP ships Purchase roles.
PROCESS_COST_WORKFLOW = "Process Cost Workflow"
WORKFLOW_ROLE_MAP = {"Purchase User": "Merch User", "Purchase Manager": "Merch Manager"}
# Report -> roles production allowed to run it.
MRP_REPORT_ROLES = {"YRP Stock Balance": ("Merch User", "Merch Manager")}


def ensure_mrp_role_permissions():
	"""Match production MRP role access on shared YRP DocTypes and reports."""
	for doctype, grants in MRP_ROLE_GRANTS.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		for role, permission_types in grants.items():
			grant_permissions(doctype, role, permission_types)
		frappe.clear_cache(doctype=doctype)
	for doctype, roles in MRP_ROLE_REVOKES.items():
		if frappe.db.exists("DocType", doctype):
			revoke_permissions(doctype, roles)
	for report, roles in MRP_REPORT_ROLES.items():
		if frappe.db.exists("Report", report):
			add_report_roles(report, roles)
	if frappe.db.exists("Workflow", PROCESS_COST_WORKFLOW):
		map_workflow_roles(PROCESS_COST_WORKFLOW)


def grant_permissions(doctype, role, permission_types):
	filters = {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
	# Frappe copies the standard rows before the first custom grant.
	name = frappe.db.get_value("Custom DocPerm", filters, "name") or add_permission(doctype, role)
	# add_permission returns None when copying the standard rows already created the role row.
	name = name or frappe.db.get_value("Custom DocPerm", filters, "name")
	frappe.db.set_value("Custom DocPerm", name, {ptype: 1 for ptype in permission_types})


def revoke_permissions(doctype, roles):
	setup_custom_perms(doctype)
	for name in frappe.get_all("Custom DocPerm", filters={"parent": doctype, "role": ["in", roles]}, pluck="name"):
		frappe.delete_doc("Custom DocPerm", name, ignore_permissions=True)
	frappe.clear_cache(doctype=doctype)


def add_report_roles(report, roles):
	custom_role_name = frappe.db.get_value("Custom Role", {"report": report}, "name")
	if custom_role_name:
		custom_role = frappe.get_doc("Custom Role", custom_role_name)
	else:
		report_doc = frappe.get_doc("Report", report)
		custom_role = frappe.get_doc(
			{
				"doctype": "Custom Role",
				"report": report,
				"ref_doctype": report_doc.ref_doctype,
				"roles": [{"role": row.role} for row in report_doc.roles if row.role],
			}
		)
	existing = {row.role for row in custom_role.roles}
	for role in roles:
		if role not in existing:
			custom_role.append("roles", {"role": role})
	custom_role.save(ignore_permissions=True)
	frappe.clear_cache(doctype="Report")


def map_workflow_roles(workflow_name):
	workflow = frappe.get_doc("Workflow", workflow_name)
	rows = [(row, "allowed") for row in workflow.transitions] + [(row, "allow_edit") for row in workflow.states]
	stale = [(row, field) for row, field in rows if row.get(field) in WORKFLOW_ROLE_MAP]
	for row, field in stale:
		row.set(field, WORKFLOW_ROLE_MAP[row.get(field)])
	if stale:
		workflow.save(ignore_permissions=True)
