import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	approve_grammage,
	get_web_laysheet,
)

APPROVER = "cls.grammage.approver@test.local"
READER = "cls.grammage.reader@test.local"


class TestCLSGrammageApproval(IntegrationTestCase):
	"""Approval role, not LaySheet write access, decides who approves grammage."""

	def setUp(self):
		self.laysheet = frappe.db.get_value(
			"SD YRP Cutting LaySheet",
			{"status": "Approval Pending", "docstatus": 0, "cutting_plan": ["is", "set"]},
			["name", "cutting_plan"],
			as_dict=True,
		)
		if not self.laysheet:
			self.skipTest("No Approval Pending Cutting LaySheet on this site")
		settings = frappe.get_single("SD YRP MRP Settings")
		if "Merch Manager" not in {row.role for row in settings.cls_grammage_approval_roles}:
			settings.append("cls_grammage_approval_roles", {"role": "Merch Manager"})
			settings.save(ignore_permissions=True)
		make_user(APPROVER, ["Merch User", "Merch Manager"])
		make_user(READER, ["Merch User"])

	def tearDown(self):
		frappe.set_user("Administrator")

	def get_permissions(self):
		return get_web_laysheet(cutting_plan=self.laysheet.cutting_plan, cutting_laysheet=self.laysheet.name)[
			"permissions"
		]

	def test_read_only_approver_sees_and_runs_approval(self):
		frappe.set_user(APPROVER)
		self.assertFalse(frappe.has_permission("SD YRP Cutting LaySheet", "write"))
		self.assertTrue(self.get_permissions()["can_approve"])

		approve_grammage(self.laysheet.name)

		status, approved_by = frappe.db.get_value(
			"SD YRP Cutting LaySheet", self.laysheet.name, ["status", "approved_by"]
		)
		self.assertEqual((status, approved_by), ("Bundles Generated", APPROVER))

	def test_user_without_approval_role_cannot_approve(self):
		frappe.set_user(READER)
		self.assertFalse(self.get_permissions()["can_approve"])
		with self.assertRaisesRegex(frappe.ValidationError, "required role to approve grammage"):
			approve_grammage(self.laysheet.name)


def make_user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	user.add_roles(*roles)
