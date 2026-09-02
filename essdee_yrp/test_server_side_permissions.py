from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from essdee_yrp import ipd_ui, production_order_workflow
from essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan_dispatch import (
	sd_yrp_finishing_plan_dispatch as finishing_plan_dispatch,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item import (
	sd_yrp_grn_rework_item as grn_rework_item,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_mrp_data_migration import (
	sd_yrp_mrp_data_migration as mrp_data_migration,
)
from yrp.yrp.doctype.yrp_inspection_entry import yrp_inspection_entry as inspection_entry


class TestServerSidePermissions(UnitTestCase):
	"""Prove sensitive whitelisted actions authorize before doing any work."""

	def test_inspection_conversion_rejects_roleless_call_before_document_load(self):
		with (
			patch.object(inspection_entry, "_approver_role", return_value="Stock Manager"),
			patch.object(inspection_entry.frappe, "get_roles", return_value=[]),
			patch.object(inspection_entry.frappe, "get_doc") as get_doc,
		):
			with self.assertRaises(frappe.PermissionError):
				inspection_entry.convert_stock("INS-U43")

		get_doc.assert_not_called()

	def test_ppo_request_rejects_missing_action_role_before_lock_or_load(self):
		with (
			patch.object(
				production_order_workflow,
				"get_ppo_action_roles",
				return_value={"Merch User"},
			),
			patch.object(production_order_workflow.frappe, "get_roles", return_value=[]),
			patch.object(production_order_workflow, "lock_production_orders") as lock,
			patch.object(production_order_workflow.frappe, "get_doc") as get_doc,
		):
			with self.assertRaises(frappe.PermissionError):
				production_order_workflow.request_ppo_approval("PPO-U43")

		lock.assert_not_called()
		get_doc.assert_not_called()

	def test_ppo_approval_rejects_missing_approver_role_before_lock_or_load(self):
		with (
			patch.object(
				production_order_workflow,
				"get_ppo_approver_roles",
				return_value={"Merch Manager"},
			),
			patch.object(production_order_workflow, "user_has_any_role", return_value=False),
			patch.object(production_order_workflow, "lock_production_orders") as lock,
			patch.object(production_order_workflow.frappe, "get_doc") as get_doc,
		):
			with self.assertRaises(frappe.PermissionError):
				production_order_workflow.approve_ppo("PPO-U43")

		lock.assert_not_called()
		get_doc.assert_not_called()

	def test_ipd_approval_and_revert_reject_missing_role_before_document_load(self):
		with (
			patch.object(ipd_ui, "get_approval_roles", return_value=["Senior Merch"]),
			patch.object(ipd_ui.frappe, "get_roles", return_value=[]),
			patch.object(ipd_ui.frappe, "get_doc") as get_doc,
		):
			for action in (ipd_ui.approve_ipd, ipd_ui.revert_ipd_approval):
				with self.subTest(action=action.__name__):
					with self.assertRaises(frappe.PermissionError):
						action("IPD-U43")

		get_doc.assert_not_called()

	def test_rework_sync_requires_source_read_and_target_create_permission(self):
		grn = MagicMock()
		with (
			patch.object(grn_rework_item.frappe, "get_doc", return_value=grn),
			patch.object(grn_rework_item.frappe, "has_permission", return_value=False),
			patch.object(grn_rework_item, "sync_grn_rework") as sync,
		):
			with self.assertRaises(frappe.PermissionError):
				grn_rework_item.sync_grn_rework_for_name("GRN-U43")

		grn.check_permission.assert_called_once_with("read")
		sync.assert_not_called()

	def test_rework_mutation_requires_parent_write_permission(self):
		parent = MagicMock()
		parent.check_permission.side_effect = frappe.PermissionError("Not permitted")
		with (
			patch.object(grn_rework_item.frappe, "get_all", return_value=["RW-U43"]),
			patch.object(grn_rework_item.frappe, "get_doc", return_value=parent),
		):
			with self.assertRaises(frappe.PermissionError):
				grn_rework_item._load_action_rows('[{"row_name": "ROW-U43"}]')

		parent.check_permission.assert_called_once_with("write")

	def test_migration_actions_require_system_manager_before_write_permission(self):
		doc = MagicMock()
		with patch.object(
			mrp_data_migration.frappe,
			"only_for",
			side_effect=frappe.PermissionError("Not permitted"),
		) as only_for:
			with self.assertRaises(frappe.PermissionError):
				mrp_data_migration.MRPDataMigration._check_action_access(doc)

		only_for.assert_called_once_with("System Manager")
		doc.check_permission.assert_not_called()

	def test_migration_connection_defaults_require_system_manager_before_config_load(self):
		with (
			patch.object(
				mrp_data_migration.frappe,
				"only_for",
				side_effect=frappe.PermissionError("Not permitted"),
			),
			patch.object(mrp_data_migration, "get_migration_settings") as get_settings,
		):
			with self.assertRaises(frappe.PermissionError):
				mrp_data_migration.get_connection_defaults()

		get_settings.assert_not_called()

	def test_dispatch_requires_write_permission_before_stock_document_creation(self):
		dispatch = MagicMock()
		dispatch.check_permission.side_effect = frappe.PermissionError("Not permitted")
		with (
			patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=dispatch),
			patch.object(finishing_plan_dispatch.frappe, "new_doc") as new_doc,
		):
			with self.assertRaises(frappe.PermissionError):
				finishing_plan_dispatch.create_stock_dispatch(
					"FPD-U43", "FROM-U43", "TO-U43", "TN-U43", 1
				)

		dispatch.check_permission.assert_called_once_with("write")
		new_doc.assert_not_called()


class TestActualRolelessSession(IntegrationTestCase):
	def test_whitelisted_sensitive_actions_reject_an_actual_roleless_session(self):
		grn = frappe.get_all(
			'YRP Goods Received Note', filters={"docstatus": 1}, pluck="name", limit=1
		)[0]
		dispatch = frappe.get_all(
			'SD YRP Finishing Plan Dispatch', filters={"docstatus": 1}, pluck="name", limit=1
		)[0]
		user = f"u43-{frappe.generate_hash(length=10)}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": user,
				"first_name": "U43 Roleless",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

		original_user = frappe.session.user
		try:
			frappe.set_user(user)
			checks = {
				"inspection conversion": lambda: inspection_entry.convert_stock("INS-U43"),
				"PPO request": lambda: production_order_workflow.request_ppo_approval("PPO-U43"),
				"PPO approval": lambda: production_order_workflow.approve_ppo("PPO-U43"),
				"IPD approval": lambda: ipd_ui.approve_ipd("IPD-U43"),
				"migration configuration": mrp_data_migration.get_connection_defaults,
				"rework sync": lambda: grn_rework_item.sync_grn_rework_for_name(grn),
				"stock dispatch": lambda: finishing_plan_dispatch.create_stock_dispatch(
					dispatch, "FROM-U43", "TO-U43", "TN-U43", 1
				),
			}
			for label, action in checks.items():
				with self.subTest(action=label):
					with self.assertRaises(frappe.PermissionError):
						action()
		finally:
			frappe.set_user(original_user)
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, force=True, ignore_permissions=True)
