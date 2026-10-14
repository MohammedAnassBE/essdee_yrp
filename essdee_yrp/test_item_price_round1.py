from unittest import TestCase

import frappe


class TestPurchaseItemPermissionPatch(TestCase):
	permission_fields = (
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

	def setUp(self):
		self.savepoint = "permission_patch_" + frappe.generate_hash(length=8)
		frappe.db.savepoint(self.savepoint)

	def tearDown(self):
		frappe.db.rollback(save_point=self.savepoint)
		for doctype in (
			"Item",
			"YRP Item Item Attribute Mapping",
			"YRP Item Attribute Value",
			"Item Attribute",
		):
			frappe.clear_cache(doctype=doctype)

	def test_patch_is_idempotent_and_preserves_unrelated_role_rights(self):
		from essdee_yrp.patches.grant_purchase_item_permissions import (
			PERMISSION_GRANTS,
			execute,
		)

		before = self._unrelated_permissions(PERMISSION_GRANTS)
		execute()
		execute()

		self.assertEqual(self._unrelated_permissions(PERMISSION_GRANTS), before)
		for doctype, grants in PERMISSION_GRANTS.items():
			for role, permission_types in grants.items():
				permission = frappe.db.get_value(
					"Custom DocPerm",
					{
						"parent": doctype,
						"role": role,
						"permlevel": 0,
						"if_owner": 0,
					},
					list(self.permission_fields),
					as_dict=True,
				)
				self.assertTrue(permission, f"Missing {doctype} permission for {role}")
				for permission_type in permission_types:
					self.assertEqual(
						permission.get(permission_type),
						1,
						f"{doctype} {role} lacks {permission_type}",
					)

	def test_new_grant_has_only_requested_permission_types(self):
		from essdee_yrp.patches.grant_purchase_item_permissions import (
			PERMISSION_GRANTS,
			execute,
		)

		doctype = "Item Attribute"
		role = "Purchase Manager"
		filters = {
			"parent": doctype,
			"role": role,
			"permlevel": 0,
			"if_owner": 0,
		}
		frappe.db.delete("Custom DocPerm", filters)
		execute()

		permission = frappe.db.get_value(
			"Custom DocPerm", filters, list(self.permission_fields), as_dict=True
		)
		expected = set(PERMISSION_GRANTS[doctype][role])
		self.assertTrue(permission)
		for permission_type in self.permission_fields:
			self.assertEqual(permission.get(permission_type) or 0, int(permission_type in expected))

	def test_owner_only_rule_is_not_changed_instead_of_unrestricted_rule(self):
		from essdee_yrp.patches.grant_purchase_item_permissions import execute

		doctype = "YRP Item Item Attribute Mapping"
		role = "Item Manager"
		unrestricted_filters = {
			"parent": doctype,
			"role": role,
			"permlevel": 0,
			"if_owner": 0,
		}
		frappe.db.delete("Custom DocPerm", unrestricted_filters)
		unrestricted = frappe.get_doc(
			{
				"doctype": "Custom DocPerm",
				"parent": doctype,
				"parenttype": "DocType",
				"parentfield": "permissions",
				"role": role,
				"permlevel": 0,
				"if_owner": 0,
				"read": 1,
			}
		).insert(ignore_permissions=True).name
		owner = frappe.db.get_value(
			"Custom DocPerm",
			{
				"parent": doctype,
				"role": role,
				"permlevel": 0,
				"if_owner": 1,
			},
			"name",
		)
		if not owner:
			owner = frappe.get_doc(
				{
					"doctype": "Custom DocPerm",
					"parent": doctype,
					"parenttype": "DocType",
					"parentfield": "permissions",
					"role": role,
					"permlevel": 0,
					"if_owner": 1,
				}
			).insert(ignore_permissions=True).name
		owner_before = frappe.db.get_value(
			"Custom DocPerm", owner, list(self.permission_fields), as_dict=True
		)
		frappe.db.set_value("Custom DocPerm", unrestricted, "write", 0)

		execute()

		self.assertEqual(frappe.db.get_value("Custom DocPerm", unrestricted, "write"), 1)
		self.assertEqual(
			frappe.db.get_value(
				"Custom DocPerm", owner, list(self.permission_fields), as_dict=True
			),
			owner_before,
		)

	def _unrelated_permissions(self, grants):
		target_roles = {
			doctype: set(doctype_grants) for doctype, doctype_grants in grants.items()
		}
		permissions = {}
		for doctype in grants:
			meta = frappe.get_meta(doctype, cached=False)
			permissions[doctype] = sorted(
				(
					row.role,
					row.permlevel,
					row.if_owner,
					*(row.get(fieldname) or 0 for fieldname in self.permission_fields),
				)
				for row in meta.permissions
				if row.role not in target_roles[doctype]
			)
		return permissions
