"""Exercise source-equivalent Item Balance access through Desk."""

import json
import unittest

import frappe
from frappe.desk.query_report import run
from frappe.utils import add_months, today

REFERENCE_REPORTS = {
	"YRP Stock Reservation Entry": "SD YRP Reserved Stock",
	"YRP Stock Ledger Entry": "SD YRP Stock Ledger",
}


class TestItemBalanceReportPermissions(unittest.TestCase):
	def setUp(self):
		self.user = frappe.session.user
		frappe.set_user("Administrator")
		frappe.db.savepoint("item_balance_permissions")
		self.users = []

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="item_balance_permissions")
		for doctype in ("YRP Bin", *REFERENCE_REPORTS):
			frappe.clear_cache(doctype=doctype)
		for user in self.users:
			frappe.clear_cache(user=user)
		frappe.set_user(self.user)

	def report_user(self, role):
		user = f"_test_report_{role.lower().replace(' ', '_')}@example.com"
		self.users.append(user)
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": user,
					"first_name": "Report Permission",
					"send_welcome_email": 0,
					"roles": [{"role": role}],
				}
			).insert(ignore_permissions=True)
		return user

	def declared_roles(self, report):
		"""Return roles from the report JSON; the DB copy also holds roles added by other apps."""
		folder = frappe.scrub(report)
		path = frappe.get_module_path("Essdee YRP", "report", folder, f"{folder}.json")
		with open(path) as file:
			return [row["role"] for row in json.load(file)["roles"]]

	def test_declared_report_roles_can_execute_on_standard_doctype_grants(self):
		from essdee_yrp import setup

		for doctype in REFERENCE_REPORTS:
			# Deployed state without migrated source grants: only standard DocPerms.
			frappe.db.delete("Custom DocPerm", {"parent": doctype})
			frappe.clear_cache(doctype=doctype)
		setup.ensure_report_permissions()
		setup.ensure_report_permissions()
		filters = {"from_date": add_months(today(), -1), "to_date": today()}
		for doctype, report in REFERENCE_REPORTS.items():
			roles = self.declared_roles(report)
			self.assertTrue(roles)
			for role in roles:
				with self.subTest(report=report, role=role):
					frappe.set_user(self.report_user(role))
					self.assertTrue(frappe.has_permission(doctype, "report"))
					result = run(report, filters=filters, ignore_prepared_report=True)
					self.assertTrue(result["columns"])
					frappe.set_user("Administrator")

	def test_merch_roles_can_execute_item_balance_without_write_access(self):
		from essdee_yrp import setup

		previous = self.other_permissions()
		setup.ensure_report_permissions()
		setup.ensure_report_permissions()
		for role in ("Merch Manager", "Merch User"):
			with self.subTest(role=role):
				frappe.set_user("Administrator")
				user = f"_test_item_balance_{role.lower().replace(' ', '_')}@example.com"
				self.users.append(user)
				frappe.get_doc(
					{
						"doctype": "User",
						"email": user,
						"first_name": "Report Permission",
						"send_welcome_email": 0,
						"roles": [{"role": role}],
					}
				).insert(ignore_permissions=True)
				frappe.set_user(user)
				self.assertTrue(frappe.has_permission("YRP Bin", "report"))
				self.assertTrue(frappe.has_permission("YRP Bin", "read"))
				for ptype in ("write", "create", "delete"):
					self.assertFalse(frappe.has_permission("YRP Bin", ptype))
				result = run(
					"SD YRP Item Balance", filters={"lot": "C0925-57/1"}, ignore_prepared_report=True
				)
				self.assertTrue(result["columns"])
				self.assertTrue(result["result"])
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.count(
				"Custom DocPerm",
				{
					"parent": "YRP Bin",
					"role": ["in", ["Merch Manager", "Merch User"]],
					"permlevel": 0,
					"if_owner": 0,
				},
			),
			2,
		)
		self.assertEqual(self.other_permissions(), previous)

	def other_permissions(self):
		from essdee_yrp.setup import DOCPERM_FIELDS

		return sorted(
			(row.role, row.permlevel, row.if_owner, *(row.get(field) for field in DOCPERM_FIELDS))
			for row in frappe.get_meta("YRP Bin").permissions
			if row.role not in ("Merch Manager", "Merch User")
		)
