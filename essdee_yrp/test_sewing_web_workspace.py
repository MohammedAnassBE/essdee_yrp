from importlib import import_module
from importlib.util import find_spec
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp import hooks
from essdee_yrp.www.web import WEB_DOCTYPES, _apply_accurate_web_perms


class TestSewingWebWorkspace(TestCase):
	def _workspace(self):
		module = "essdee_yrp.sewing.web_workspace"
		self.assertIsNotNone(find_spec(module), "The Sewing web capability endpoint must exist")
		return import_module(module)

	def _capabilities(self, denied=(), allowed=None):
		workspace = self._workspace()

		def has_permission(doctype, ptype="read", **_kwargs):
			if allowed is not None:
				return (doctype, ptype) in allowed
			return (doctype, ptype) not in denied

		with patch.object(frappe, "has_permission", side_effect=has_permission):
			return workspace.get_capabilities()

	def test_capabilities_expose_server_owned_sections_actions_and_reports(self):
		payload = self._capabilities()
		self.assertEqual(set(payload), {"sections", "plan_actions", "reports"})
		self.assertEqual(
			{key: value["label"] for key, value in payload["sections"].items()},
			{
				"plans": "Sewing Plan",
				"work_orders": "Work Orders",
				"reports": "Reports",
				"attendance": "Attendance Report",
			},
		)
		self.assertEqual(
			{key: (value["label"], value["doctype"]) for key, value in payload["plan_actions"].items()},
			{
				"entry": ("Sewing Plan Entry", "SD YRP Sewing Plan Entry Detail"),
				"plan": ("Sewing Plan", "SD YRP Sewing Plan"),
				"goods_received_note": ("Goods Received Note", "YRP Goods Received Note"),
			},
		)
		self.assertEqual(
			{key: value["label"] for key, value in payload["reports"].items()},
			{
				"status_summary": "Status Summary",
				"dpr": "DPR",
				"scr": "SCR",
				"monthly_summary": "Monthly Summary",
				"item_summary": "Item Summary",
				"finishing_dispatch": "Finishing Plan Dispatch",
				"lot_cut_quantity": "Lot Cut Quantity",
				"inhouse_quantity": "In-house Quantity",
				"grn_report": "GRN Report",
				"grn_summary": "GRN Summary",
				"dc_report": "DC Report",
				"stock_entry_report": "Stock Entry Report",
				"stock_reconciliation_report": "Stock Reconciliation Report",
				"stock_update_report": "Stock Update Report",
				"finishing_inward_updates": "Finishing Inward Updates",
			},
		)

	def test_finishing_dispatch_report_requires_both_source_read_permissions(self):
		base = {
			("SD YRP Sewing Plan", "read"),
			("SD YRP Sewing Plan", "report"),
			("SD YRP Finishing Plan", "read"),
			("YRP Goods Received Note", "read"),
		}
		payload = self._capabilities(allowed=base)
		self.assertEqual(payload["reports"]["finishing_dispatch"]["label"], "Finishing Plan Dispatch")

		for missing in (("SD YRP Finishing Plan", "read"), ("YRP Goods Received Note", "read")):
			with self.subTest(missing=missing):
				payload = self._capabilities(allowed=base - {missing})
				self.assertNotIn("finishing_dispatch", payload["reports"])
				self.assertIn("status_summary", payload["reports"])

	def test_lot_cut_quantity_follows_sewing_report_access(self):
		base = {("SD YRP Sewing Plan", "read"), ("SD YRP Sewing Plan", "report")}
		capability = self._capabilities(allowed=base)["reports"]["lot_cut_quantity"]
		self.assertIs(capability["can_read_cutting_plan"], False)
		capability = self._capabilities(allowed=base | {("SD YRP Cutting Plan", "read")})["reports"]["lot_cut_quantity"]
		self.assertIs(capability["can_read_cutting_plan"], True)
		self.assertNotIn("lot_cut_quantity", self._capabilities(allowed={("SD YRP Sewing Plan", "read")})["reports"])

	def test_inhouse_quantity_requires_work_order_and_lot_read(self):
		base = {
			("SD YRP Sewing Plan", "read"),
			("SD YRP Sewing Plan", "report"),
			("YRP Work Order", "read"),
			("SD YRP Lot", "read"),
		}
		self.assertEqual(
			self._capabilities(allowed=base)["reports"]["inhouse_quantity"]["label"], "In-house Quantity"
		)
		for missing in (("YRP Work Order", "read"), ("SD YRP Lot", "read")):
			with self.subTest(missing=missing):
				self.assertNotIn("inhouse_quantity", self._capabilities(allowed=base - {missing})["reports"])

	def test_capabilities_omit_all_unreadable_sections(self):
		payload = self._capabilities(allowed=set())
		self.assertEqual(payload["sections"], {})
		self.assertEqual(payload["reports"], {})
		for action in payload["plan_actions"].values():
			for flag in ("read", "create", "write", "delete", "submit", "report"):
				self.assertIs(action[f"can_{flag}"], False)

	def test_report_and_attendance_sections_require_plan_read_and_report(self):
		for denied_permission, expected_sections in (
			("read", {"work_orders"}),
			("report", {"plans", "work_orders"}),
		):
			with self.subTest(denied_permission=denied_permission):
				payload = self._capabilities(denied={("SD YRP Sewing Plan", denied_permission)})
				self.assertEqual(set(payload["sections"]), expected_sections)
				self.assertEqual(payload["reports"], {})

	def test_work_orders_require_independent_work_order_read_permission(self):
		payload = self._capabilities(allowed={("YRP Work Order", "read")})
		self.assertEqual(list(payload["sections"]), ["work_orders"])
		self.assertEqual(
			payload["sections"]["work_orders"],
			{
				"doctype": "YRP Work Order",
				"label": "Work Orders",
				"can_read": True,
				"can_create": False,
				"can_write": False,
				"can_delete": False,
				"can_submit": False,
				"can_report": False,
			},
		)

	def test_report_capabilities_never_grant_mutations(self):
		payload = self._capabilities()
		for capability in (
			payload["sections"]["reports"],
			payload["sections"]["attendance"],
			*payload["reports"].values(),
		):
			with self.subTest(label=capability["label"]):
				self.assertEqual(
					{
						key: value
						for key, value in capability.items()
						if key.startswith("can_") and key != "can_read_cutting_plan"
					},
					{
						"can_read": True,
						"can_create": False,
						"can_write": False,
						"can_delete": False,
						"can_submit": False,
						"can_report": True,
					},
				)

	def test_plan_card_derives_each_flag_from_the_operation_permission(self):
		for doctype, permission, flag in (
			("SD YRP Sewing Plan Entry Detail", "create", "can_create"),
			("SD YRP Sewing Plan", "write", "can_write"),
			("SD YRP Sewing Plan Entry Detail", "delete", "can_delete"),
			("YRP Goods Received Note", "create", "can_submit"),
			("YRP Goods Received Note", "submit", "can_submit"),
			("SD YRP Sewing Plan", "report", "can_report"),
		):
			with self.subTest(doctype=doctype, permission=permission):
				plans = self._capabilities(denied={(doctype, permission)})["sections"]["plans"]
				self.assertEqual(
					{key: value for key, value in plans.items() if key.startswith("can_")},
					{
						"can_read": True,
						"can_create": flag != "can_create",
						"can_write": flag != "can_write",
						"can_delete": flag != "can_delete",
						"can_submit": flag != "can_submit",
						"can_report": flag != "can_report",
						"can_update_fi_dates": True,
					},
				)

	def test_fi_date_capability_follows_the_production_planner_role(self):
		for roles, expected in (
			(["System Manager"], True),
			(["Production Planner"], True),
			(["Sewing User"], False),
		):
			with self.subTest(roles=roles), patch.object(frappe, "get_roles", return_value=roles):
				self.assertIs(self._capabilities()["sections"]["plans"]["can_update_fi_dates"], expected)

	def test_resource_flags_are_independent_effective_permissions(self):
		resources = {
			"entry": "SD YRP Sewing Plan Entry Detail",
			"plan": "SD YRP Sewing Plan",
			"goods_received_note": "YRP Goods Received Note",
		}
		permissions = ("read", "create", "write", "delete", "submit", "report")
		for resource, doctype in resources.items():
			for permission in permissions:
				with self.subTest(resource=resource, permission=permission):
					payload = self._capabilities(allowed={(doctype, permission)})
					for action_key, action in payload["plan_actions"].items():
						for ptype in permissions:
							self.assertIs(
								action[f"can_{ptype}"],
								action_key == resource and ptype == permission,
							)

	def test_sewing_doctypes_are_registered_in_both_web_catalogs(self):
		for doctype in ("SD YRP Sewing Plan", "SD YRP Sewing Plan Entry Detail"):
			for catalog in (WEB_DOCTYPES, hooks.yrp_web_doctype_catalog):
				with self.subTest(doctype=doctype, catalog=catalog):
					self.assertIn(doctype, catalog)

	def test_web_boot_corrects_sewing_permissions_using_effective_access(self):
		doctypes = ["SD YRP Sewing Plan", "SD YRP Sewing Plan Entry Detail"]
		user = {f"can_{ptype}": doctypes[:] for ptype in ("read", "create", "write", "delete", "submit")}
		with patch.object(frappe, "has_permission", return_value=False):
			_apply_accurate_web_perms(user)
		for flag, allowed in user.items():
			with self.subTest(flag=flag):
				self.assertFalse(set(doctypes) & set(allowed))

	def test_capability_endpoint_is_whitelisted_only_for_authenticated_users(self):
		endpoint = self._workspace().get_capabilities
		self.assertIn(endpoint, frappe.whitelisted)
		self.assertNotIn(endpoint, frappe.guest_methods)
		original_user = frappe.session.user
		try:
			frappe.set_user("Guest")
			with self.assertRaises(frappe.PermissionError):
				frappe.is_whitelisted(endpoint)
			frappe.set_user("Administrator")
			frappe.is_whitelisted(endpoint)
		finally:
			frappe.set_user(original_user)
