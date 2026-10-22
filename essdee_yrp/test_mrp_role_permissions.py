import frappe
from frappe.permissions import rights
from frappe.tests import IntegrationTestCase

from essdee_yrp.mrp_role_permissions import (
	MRP_REPORT_ROLES,
	MRP_ROLE_GRANTS,
	MRP_ROLE_REVOKES,
	PROCESS_COST_WORKFLOW,
	WORKFLOW_ROLE_MAP,
	ensure_mrp_role_permissions,
)


class TestMrpRolePermissions(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_mrp_role_permissions()

	def role_permissions(self, doctype, role):
		frappe.clear_cache(doctype=doctype)
		rows = [row for row in frappe.get_meta(doctype).permissions if row.role == role and not row.permlevel]
		return {ptype: any(row.get(ptype) for row in rows) for ptype in rights}

	def test_floor_roles_get_production_doctype_rights(self):
		for doctype, grants in MRP_ROLE_GRANTS.items():
			for role, permission_types in grants.items():
				permissions = self.role_permissions(doctype, role)
				for ptype in permission_types:
					with self.subTest(doctype=doctype, role=role, ptype=ptype):
						self.assertTrue(permissions.get(ptype))

	def test_store_user_keeps_stock_user_rows_on_converted_doctypes(self):
		self.assertTrue(self.role_permissions("YRP Delivery Challan", "Stock User").get("submit"))
		self.assertTrue(self.role_permissions("YRP Goods Received Note", "Stock User").get("submit"))

	def test_purchase_roles_lose_rights_production_never_gave(self):
		for doctype, roles in MRP_ROLE_REVOKES.items():
			for role in roles:
				with self.subTest(doctype=doctype, role=role):
					permissions = self.role_permissions(doctype, role)
					self.assertFalse(any(permissions.get(ptype) for ptype in ("read", "create", "write")))
		self.assertTrue(self.role_permissions("YRP Process Cost", "Merch Manager").get("write"))

	def test_purchase_user_prints_excel_stickers(self):
		permissions = self.role_permissions("YRP Excel Sticker Print", "Purchase User")
		self.assertTrue(all(permissions[ptype] for ptype in ("read", "write", "create", "submit", "print")))
		self.assertFalse(permissions["cancel"] or permissions["delete"])

	def test_merch_roles_run_stock_balance(self):
		for report, roles in MRP_REPORT_ROLES.items():
			custom_role = frappe.get_doc("Custom Role", {"report": report})
			self.assertTrue(set(roles) <= {row.role for row in custom_role.roles})

	def test_process_cost_workflow_uses_merch_roles(self):
		workflow = frappe.get_doc("Workflow", PROCESS_COST_WORKFLOW)
		roles = {row.allowed for row in workflow.transitions} | {row.allow_edit for row in workflow.states}
		self.assertFalse(roles & set(WORKFLOW_ROLE_MAP))
		approvers = {row.allowed for row in workflow.transitions if row.action == "Approve"}
		self.assertEqual(approvers, {"Merch Manager"})

	def test_rerun_is_idempotent(self):
		before = frappe.db.count("Custom DocPerm", {"parent": "YRP Delivery Challan"})
		ensure_mrp_role_permissions()
		self.assertEqual(frappe.db.count("Custom DocPerm", {"parent": "YRP Delivery Challan"}), before)
