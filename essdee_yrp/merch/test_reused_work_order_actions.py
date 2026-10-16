from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.fabric_store.documents import work_order


class TestMerchReusedWorkOrderActions(TestCase):
	def setUp(self):
		self.roles = []
		self.settings = {
			"work_order_closing_approver_role": "Merch Manager",
			"debit_request_role": "Merch User",
			"debit_approval_role": "",
		}
		self.doc = frappe._dict(name="WO-TEST", docstatus=1, open_status="Open", modified="now")
		patches = (
			patch.object(frappe, "session", frappe._dict(user="merch-test@example.com")),
			patch.object(frappe, "get_roles", side_effect=lambda user: self.roles),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(work_order.attribute_db, "get_single_value", side_effect=lambda doctype, field: self.settings.get(field)),
		)
		for mocked in patches:
			mocked.start()
			self.addCleanup(mocked.stop)

	def capabilities(self):
		return work_order._capability_candidates(self.doc, {}, {}, work_order.get_close_permission())

	def test_closing_and_debit_actions_follow_settings_roles(self):
		for role, manager, debit in (("Merch User", False, True), ("Merch Manager", True, False)):
			with self.subTest(role=role):
				self.roles = [role]
				self.doc.open_status = "Open"
				actions = self.capabilities()
				self.assertEqual(actions["request_close"]["eligible"], not manager)
				self.assertEqual(actions["close"]["eligible"], manager)
				self.assertEqual(actions["create_debit"]["eligible"], debit)
				self.doc.open_status = "Close Request"
				self.assertEqual(self.capabilities()["approve_close"]["eligible"], manager)

	def test_empty_closing_role_hides_close_and_request_close(self):
		self.settings["work_order_closing_approver_role"] = ""
		for role in ("Merch User", "Merch Manager", "System Manager"):
			with self.subTest(role=role):
				self.roles = [role]
				actions = self.capabilities()
				self.assertFalse(actions["request_close"]["eligible"])
				self.assertFalse(actions["close"]["eligible"])

	def test_empty_debit_approval_role_hides_approval_during_close(self):
		for role in ("Merch User", "Merch Manager", "System Manager"):
			with (
				self.subTest(role=role),
				patch.object(work_order, "_get_work_order", return_value=self.doc),
				patch.object(work_order, "get_debits", return_value=[]),
			):
				self.roles = [role]
				context = work_order.execute_work_order_command("WO-TEST", "get_close_context", expected_modified="now")
				self.assertFalse(context["can_approve_debit"])
				self.assertEqual(context["can_create_debit"], role == "Merch Manager")

	def test_close_execution_rechecks_the_settings_role(self):
		self.roles = ["Merch User"]
		with self.assertRaises(frappe.PermissionError):
			work_order._assert_close_command(self.doc, "close")
		work_order._assert_close_command(self.doc, "request_close")
		self.roles = ["Merch Manager"]
		work_order._assert_close_command(self.doc, "close")
