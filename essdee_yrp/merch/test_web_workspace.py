from unittest import TestCase
from unittest.mock import call, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.merch import web_workspace
from essdee_yrp.merch_purchase import web_workspace as merch_purchase_workspace

MERCH_USER = "merch.cutting.plan@example.test"


class TestMerchWebWorkspace(TestCase):
	@patch("essdee_yrp.merch.web_workspace.frappe.has_permission")
	def test_lots_capability_uses_lot_read_and_create_independently(self, has_permission):
		for can_read, can_create in ((True, True), (True, False), (False, True), (False, False)):
			with self.subTest(can_read=can_read, can_create=can_create):
				has_permission.side_effect = lambda doctype, ptype, doc=None: (
					doctype == "SD YRP Lot" and {"read": can_read, "create": can_create}.get(ptype, False)
				)
				self.assertEqual(web_workspace.get_capabilities()["sections"]["lots"], {
					"label": "Lot", "can_read": can_read, "can_create": can_create,
				})

	@patch.dict(web_workspace.REPORTS)
	@patch("essdee_yrp.merch.web_workspace.frappe.has_permission", return_value=False)
	def test_reports_card_and_tab_follow_callable_access(self, has_permission):
		for allowed in (True, False):
			with self.subTest(allowed=allowed):
				web_workspace.REPORTS["work_in_progress"] = ("Work In Progress", lambda: allowed)
				capabilities = web_workspace.get_capabilities()
				self.assertEqual(capabilities["sections"]["reports"], {
					"label": "Reports", "can_read": allowed, "can_create": False,
				})
				self.assertEqual(capabilities["reports"]["work_in_progress"], {
					"label": "Work In Progress", "can_read": allowed,
				})

	def test_shared_reports_reuse_source_department_access(self):
		self.assertEqual({key: label for key, (label, _access) in web_workspace.REPORTS.items()}, {
			"work_in_progress": "Work In Progress", "inward_quantity": "Inward Quantity", "work_order": "Work Order",
			"planning_work_in_progress": "Work In Progress", "size_wise_stock": "Size-wise Stock",
			"multi_ccr": "Multi CCR", "ppo_report": "PPO Report",
		})
		with (
			patch("essdee_yrp.merch.web_workspace.get_cutting_report_permissions", return_value={"multi-ccr": False}),
			patch("essdee_yrp.merch.web_workspace.can_run_desk_report", return_value=True) as desk_report,
			patch("essdee_yrp.merch.web_workspace.frappe.has_permission", return_value=False),
		):
			self.assertFalse(web_workspace.REPORTS["multi_ccr"][1]())
			self.assertTrue(web_workspace.REPORTS["work_order"][1]())
			self.assertFalse(web_workspace.REPORTS["ppo_report"][1]())
		desk_report.assert_called_once_with("SD YRP Work Order Report")

	@patch("essdee_yrp.merch.web_workspace.frappe.has_permission")
	def test_process_costs_capability(self, has_permission):
		has_permission.side_effect = lambda doctype, ptype, doc=None: doctype == "YRP Process Cost" and ptype == "read"
		self.assertEqual(web_workspace.get_capabilities()["sections"]["process_costs"], {
			"label": "Process Cost", "can_read": True, "can_create": False,
		})

	@patch("essdee_yrp.merch.web_workspace.frappe.has_permission", return_value=True)
	def test_readable_section_has_label(self, has_permission):
		self.assertEqual(
			web_workspace.get_capabilities()["sections"]["item_production_details"],
			{
				"label": "Item Production Detail",
				"can_read": True,
				"can_create": True,
			},
		)
		has_permission.assert_has_calls([
			call("YRP Item Production Detail", ptype="read", doc=None),
			call("YRP Item Production Detail", ptype="create", doc=None),
		])

	@patch("essdee_yrp.merch.web_workspace.frappe.has_permission", return_value=False)
	def test_no_permission_keeps_section(self, has_permission):
		section = web_workspace.get_capabilities()["sections"]["item_production_details"]
		self.assertIs(section["can_read"], False)
		self.assertIs(section["can_create"], False)

	@patch("essdee_yrp.merch.web_workspace.frappe.has_permission")
	def test_create_permission_is_independent(self, has_permission):
		for can_read, can_create in ((True, False), (False, True)):
			with self.subTest(can_read=can_read, can_create=can_create):
				has_permission.side_effect = lambda doctype, ptype, doc=None: can_read if ptype == "read" else can_create
				section = web_workspace.get_capabilities()["sections"]["item_production_details"]
				self.assertIs(section["can_read"], can_read)
				self.assertIs(section["can_create"], can_create)

	@patch("essdee_yrp.merch.web_workspace.frappe.has_permission")
	def test_reused_sections_use_their_doctype_permissions(self, has_permission):
		sections = {
			"production_orders": ("Production Order", "YRP Production Order"),
			"work_orders": ("Work Order", "YRP Work Order"),
			"bill_tracking": ("Vendor Bill Tracking", "YRP Bill Tracking"),
			"purchase_invoices": ("Purchase Invoice", "YRP Purchase Invoice"),
		}
		for key, (label, doctype) in sections.items():
			for permission in ("read", "create", None):
				with self.subTest(key=key, permission=permission):
					has_permission.side_effect = lambda target, ptype, doc=None: target == doctype and ptype == permission
					result = web_workspace.get_capabilities()["sections"]
					self.assertEqual(result[key], {
						"label": label, "can_read": permission == "read", "can_create": permission == "create",
					})
					for other in sections.keys() - {key}:
						self.assertFalse(result[other]["can_read"])


class TestMerchCuttingPlanCard(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_merch_user_reads_cutting_plans_without_creating_them(self):
		if frappe.db.exists("User", MERCH_USER):
			user = frappe.get_doc("User", MERCH_USER)
			user.set("roles", [])
		else:
			user = frappe.get_doc({"doctype": "User", "email": MERCH_USER, "first_name": "Merch Cutting", "send_welcome_email": 0})
		user.append("roles", {"role": "Merch User"})
		user.save(ignore_permissions=True)
		frappe.set_user(MERCH_USER)
		expected = {"label": "Cutting Plan", "can_read": True, "can_create": False}
		self.assertEqual(web_workspace.get_capabilities()["sections"]["cutting_plans"], expected)
		self.assertEqual(merch_purchase_workspace.get_capabilities()["sections"]["cutting_plans"], expected)
		self.assertTrue(frappe.has_permission("SD YRP Cutting Plan", "print"))
		self.assertFalse(frappe.has_permission("SD YRP Cutting Plan", "submit"))
