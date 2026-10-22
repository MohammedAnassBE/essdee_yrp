from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.cutting.web_workspace import _get_transactions
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import get_web_laysheet
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan import (
	_get_web_cutting_plan_permissions,
	get_recut_print_panel_details,
)

READ_ONLY = {"read": 1}


class TestCuttingPermissions(TestCase):
	def test_plan_workspace_exposes_effective_read_permissions(self):
		plan = MagicMock()
		plan.docstatus = 1
		plan.cp_status = "Ready to Cut"
		plan.doctype = "SD YRP Cutting Plan"

		def has_permission(doctype, ptype, doc=None):
			if doc is plan:
				return ptype in {"read", "write", "print"}
			if ptype == "read":
				return doctype in {"SD YRP Cutting LaySheet", "YRP Stock Update"}
			return False

		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.frappe.has_permission",
				side_effect=has_permission,
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.has_cls_grammage_approval_role",
				return_value=False,
			),
		):
			permissions = _get_web_cutting_plan_permissions(plan)

		self.assertFalse(permissions["can_read_marker"])
		self.assertTrue(permissions["can_read_laysheet"])
		self.assertFalse(permissions["can_read_movement"])
		self.assertTrue(permissions["can_read_stock_transfers"])
		self.assertFalse(permissions["can_read_recut"])

	def test_recut_summary_requires_child_doctype_read_permission(self):
		plan = MagicMock()
		plan.check_permission = MagicMock()

		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.frappe.get_doc",
				return_value=plan,
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.frappe.has_permission"
			) as has_permission,
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.frappe.get_all"
			) as get_all,
		):
			has_permission.side_effect = PermissionError("not permitted")
			with self.assertRaises(PermissionError):
				get_recut_print_panel_details("CP-TEST", "Recut")

		has_permission.assert_called_once_with(
			"SD YRP Recut and Print Panel", "read", throw=True
		)
		get_all.assert_not_called()


class TestCuttingAccessMessages(TestCase):
	"""Capability flags for a read-only user must not pop up Frappe's 'does not have access' message."""

	def setUp(self):
		frappe.local.message_log = []
		frappe.set_user("Guest")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_plan_flags_for_read_only_user_show_no_access_message(self):
		plan = frappe.get_doc({"doctype": "SD YRP Cutting Plan", "name": "CP-QUIET", "docstatus": 1})
		with (
			patch("frappe.permissions.get_doc_permissions", return_value=READ_ONLY),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_plan.sd_yrp_cutting_plan.has_cls_grammage_approval_role",
				return_value=False,
			),
		):
			permissions = _get_web_cutting_plan_permissions(plan)

		self.assertFalse(permissions["can_write"])
		self.assertFalse(permissions["can_print"])
		self.assertEqual(frappe.local.message_log, [])

	def test_laysheet_for_read_only_user_opens_without_access_message(self):
		plan = frappe.get_doc({"doctype": "SD YRP Cutting Plan", "name": "CP-QUIET", "docstatus": 1})
		laysheet = frappe.get_doc(
			{"doctype": "SD YRP Cutting LaySheet", "name": "CLS-QUIET", "cutting_plan": "CP-QUIET", "status": "Label Printed"}
		)
		with (
			patch("frappe.permissions.get_doc_permissions", return_value=READ_ONLY),
			patch("frappe.get_doc", side_effect=lambda doctype, name: plan if doctype == plan.doctype else laysheet),
		):
			details = get_web_laysheet(cutting_plan="CP-QUIET", cutting_laysheet="CLS-QUIET")

		self.assertEqual(details["name"], "CLS-QUIET")
		self.assertFalse(details["permissions"]["can_write"])
		self.assertFalse(details["permissions"]["can_print_laysheet"])
		self.assertEqual(details["print_formats"], [])
		self.assertEqual(frappe.local.message_log, [])

	def test_unreadable_plan_transaction_is_skipped_without_access_message(self):
		challan = frappe.get_doc({"doctype": "YRP Delivery Challan", "name": "DC-QUIET", "docstatus": 1})
		with (
			patch("frappe.permissions.get_doc_permissions", return_value={}),
			patch(
				"essdee_yrp.cutting.web_workspace._transaction_references",
				return_value=[("YRP Delivery Challan", "DC-QUIET")],
			),
			patch("frappe.db.exists", return_value=True),
			patch("frappe.get_doc", return_value=challan),
		):
			transactions = _get_transactions(frappe._dict(name="CP-QUIET"))

		self.assertFalse(any(transactions.values()))
		self.assertEqual(frappe.local.message_log, [])
