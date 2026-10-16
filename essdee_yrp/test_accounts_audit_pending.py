from datetime import date
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.accounts import audit_pending


class TestAccountsAuditPending(TestCase):
	def test_can_view_requires_accounts_role_and_finishing_plan_read(self):
		for roles, readable, expected in (
			(["Stock User"], True, False),
			(["Accounts User"], False, False),
			(["Accounts User"], True, True),
			(["Accounts Manager"], True, True),
			(["System Manager"], True, True),
		):
			with self.subTest(roles=roles, readable=readable), patch.object(
				frappe, "get_roles", return_value=roles
			), patch.object(frappe, "has_permission", return_value=readable) as permission:
				self.assertEqual(audit_pending.can_view(), expected)
				if expected:
					permission.assert_called_once_with("SD YRP Finishing Plan", ptype="read")

	def test_require_access_and_runner_reject_missing_role_or_read(self):
		for roles, readable in ((["Stock User"], True), (["Accounts User"], False)):
			with self.subTest(roles=roles), patch.object(
				frappe, "get_roles", return_value=roles
			), patch.object(frappe, "has_permission", return_value=readable), patch.object(
				frappe, "get_list"
			) as get_list:
				with self.assertRaises(frappe.PermissionError):
					audit_pending.require_access()
				with self.assertRaises(frappe.PermissionError):
					audit_pending.run({})
				get_list.assert_not_called()

	def test_run_filters_columns_days_pending_and_summary(self):
		rows = [
			{"name": "FP-OLD", "audit_requested_date": "2026-10-01"},
			{"name": "FP-SEVEN", "audit_requested_date": date(2026, 10, 8)},
			{"name": "FP-SIX", "audit_requested_date": "2026-10-09"},
			{"name": "FP-TODAY", "audit_requested_date": "2026-10-15"},
			{"name": "FP-UNDATED", "audit_requested_date": None},
		]
		with patch.object(audit_pending, "require_access"), patch.object(
			frappe, "get_list", return_value=rows
		) as get_list, patch.object(audit_pending, "today", return_value="2026-10-15"):
			result = audit_pending.run({
				"lot": "LOT-1", "item": "ITEM-1",
				"from_date": "2026-10-01", "to_date": "2026-10-15",
			})
		get_list.assert_called_once_with(
			"SD YRP Finishing Plan",
			filters={
				"fp_status": "Ready for Audit", "lot": "LOT-1", "item": "ITEM-1",
				"audit_requested_date": ["between", ["2026-10-01", "2026-10-15"]],
			},
			fields=["name", "lot", "item", "work_order", "audit_requested_date", "finishing_end_date"],
			order_by="audit_requested_date asc",
			limit_page_length=0,
		)
		self.assertEqual([row["days_pending"] for row in result["result"]], [14, 7, 6, 0, None])
		self.assertEqual(result["summary"], {"plans": 5, "oldest_days": 14})
		self.assertEqual([column["fieldname"] for column in result["columns"]], [
			"name", "lot", "item", "work_order", "audit_requested_date", "days_pending", "finishing_end_date",
		])

	def test_unfiltered_empty_result_and_dependencies(self):
		with patch.object(audit_pending, "require_access"), patch.object(
			frappe, "get_list", return_value=[]
		) as get_list, patch.object(audit_pending, "today", return_value="2026-10-15"):
			result = audit_pending.run(None, progress=lambda **values: None)
		self.assertEqual(get_list.call_args.kwargs["filters"], {"fp_status": "Ready for Audit"})
		self.assertEqual(result["result"], [])
		self.assertEqual(result["summary"], {"plans": 0, "oldest_days": 0})
		self.assertEqual(audit_pending.dependency_doctypes(), [
			"SD YRP Finishing Plan", "SD YRP Lot", "Item", "YRP Work Order",
		])

	def test_dates_must_be_paired_and_ordered(self):
		for filters in (
			{"from_date": "2026-10-01"}, {"to_date": "2026-10-15"},
			{"from_date": "2026-10-15", "to_date": "2026-10-01"},
		):
			with self.subTest(filters=filters), patch.object(
				audit_pending, "require_access"
			), patch.object(frappe, "get_list") as get_list:
				with self.assertRaises(frappe.ValidationError):
					audit_pending.run(filters)
				get_list.assert_not_called()


class TestAccountsAuditPendingLiveSite(TestCase):
	def setUp(self):
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user(self.previous_user)

	def test_administrator_run_returns_column_keys(self):
		result = audit_pending.run({})
		self.assertEqual([column["fieldname"] for column in result["columns"]], [
			"name", "lot", "item", "work_order", "audit_requested_date", "days_pending", "finishing_end_date",
		])
		self.assertEqual(result["summary"]["plans"], len(result["result"]))

	def test_require_access_rejects_user_without_accounts_role(self):
		with patch.object(frappe, "get_roles", return_value=["All", "Desk User"]):
			with self.assertRaises(frappe.PermissionError):
				audit_pending.require_access()
