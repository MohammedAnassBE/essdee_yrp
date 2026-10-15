import frappe
from yrp.web_reports.jobs import run_web_report
from yrp.web_reports.registry import clear_web_report_cache, get_web_report


class PlanningReportLiveChecks:
	def setUp(self):
		super().setUp()
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		clear_web_report_cache()

	def tearDown(self):
		frappe.set_user(self.previous_user)
		clear_web_report_cache()
		super().tearDown()

	def test_administrator_gets_columns(self):
		result = run_web_report(self.report_key, self.filters)
		self.assertEqual(result["mode"], "sync")
		self.assertTrue(result["columns"])
		self.assertIn(self.expected_column, [column["fieldname"] for column in result["columns"]])

	def test_user_without_access_is_denied(self):
		frappe.set_user("Guest")
		clear_web_report_cache()
		with self.assertRaises(frappe.PermissionError):
			run_web_report(self.report_key, self.filters)

	def test_registration_is_valid(self):
		entry = get_web_report(self.report_key)
		self.assertEqual(entry.kind, "callable" if self.report_key.startswith("planning-") else "frappe_report")
		self.assertEqual(entry.background, "never")
		self.assertTrue(entry.permission_doctypes)
		dependencies = frappe.get_attr(entry.dependency_doctypes)(self.filters)
		for doctype in dependencies:
			self.assertTrue(frappe.db.exists("DocType", doctype), doctype)
