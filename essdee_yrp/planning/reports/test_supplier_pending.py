from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.planning.reports import supplier_pending as report


class TestSupplierPendingWebReport(TestCase):
	def test_can_view_needs_a_signed_in_work_order_reporter(self):
		for user, allowed, expected in (
			("Guest", True, False),
			("a@b.c", False, False),
			("a@b.c", True, True),
		):
			with self.subTest(user=user, allowed=allowed):
				with (
					patch.object(report.frappe, "session", frappe._dict(user=user)),
					patch.object(
						frappe,
						"has_permission",
						return_value=allowed,
					) as permission,
				):
					self.assertEqual(report.can_view(), expected)
				if user != "Guest":
					permission.assert_called_once_with("YRP Work Order", "report")

	def test_report_returns_the_grouped_page_payload(self):
		payload = {"supplier": "S", "supplier_name": "Supplier", "process": "P", "items": []}
		with (
			patch.object(report, "can_view", return_value=True),
			patch.object(
				report.desk_report,
				"get_supplier_pending_report",
				return_value=payload,
			) as source,
		):
			self.assertEqual(report.get_supplier_pending_report("S", "P"), payload)
		source.assert_called_once_with("S", "P")

	def test_report_rejects_users_without_access(self):
		with (
			patch.object(report, "can_view", return_value=False),
			patch.object(
				report.desk_report,
				"get_supplier_pending_report",
			) as source,
		):
			with self.assertRaises(frappe.PermissionError):
				report.get_supplier_pending_report("S", "P")
		source.assert_not_called()

	def test_report_is_whitelisted(self):
		self.assertIn(report.get_supplier_pending_report, frappe.whitelisted)
