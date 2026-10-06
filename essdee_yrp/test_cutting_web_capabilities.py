from unittest import TestCase
from unittest.mock import patch

from essdee_yrp.cutting.web_capabilities import get_capabilities


class TestCuttingWebCapabilities(TestCase):
	def test_each_workspace_uses_its_own_read_and_create_permissions(self):
		allowed = {
			("SD YRP Cutting Plan", "read"),
			("SD YRP Cutting Order", "create"),
			("SD YRP Cutting Bulk Lay Sheets", "read"),
			("SD YRP Cutting Bulk Lay Sheets", "create"),
			("SD YRP Cutting Laysheet Planner", "create"),
			("SD YRP Cutting LaySheet", "read"),
		}

		with patch(
			"essdee_yrp.cutting.web_capabilities.frappe.has_permission",
			side_effect=lambda doctype, ptype: (doctype, ptype) in allowed,
		):
			capabilities = get_capabilities()

		self.assertEqual(
			capabilities,
			{
				"cutting-plans": {"can_read": True, "can_create": False},
				"cutting-orders": {"can_read": False, "can_create": True},
				"bulk-lay-sheets": {"can_read": True, "can_create": True},
				"lay-sheet-planner": {"can_read": False, "can_create": True},
				"reports": {"can_read": True, "can_create": False},
			},
		)

	def test_readable_parent_does_not_grant_unreadable_child_workspaces(self):
		with patch(
			"essdee_yrp.cutting.web_capabilities.frappe.has_permission",
			side_effect=lambda doctype, ptype: (doctype, ptype)
			== ("SD YRP Cutting Plan", "read"),
		):
			capabilities = get_capabilities()

		self.assertTrue(capabilities["cutting-plans"]["can_read"])
		self.assertFalse(capabilities["cutting-orders"]["can_read"])
		self.assertFalse(capabilities["bulk-lay-sheets"]["can_read"])
		self.assertFalse(capabilities["lay-sheet-planner"]["can_read"])
		self.assertFalse(capabilities["reports"]["can_read"])

	def test_reports_require_an_effective_report_source_permission(self):
		def has_permission(doctype, ptype):
			return (doctype, ptype) == ("YRP Stock Ledger Entry", "read")

		with patch(
			"essdee_yrp.cutting.web_capabilities.frappe.has_permission",
			side_effect=has_permission,
		):
			capabilities = get_capabilities()

		self.assertFalse(capabilities["reports"]["can_read"])
		self.assertFalse(capabilities["reports"]["can_create"])
