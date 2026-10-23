from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from yrp.web_reports.background import needs_background
from yrp.web_reports.jobs import execute_report_job, get_report_job, run_web_report
from yrp.web_reports.registry import clear_web_report_cache, get_web_report

RANGE_REPORTS = {
	"dc-report": 92,
	"jobwork-issued-items": 92,
	"non-jobwork-issued-items": 92,
	"non-grn-received-items": 92,
	"grn-report": 92,
	"stock-entry-report": 92,
	"grn-summary": 366,
	"stock-reconciliation-report": 366,
}
ALWAYS_REPORTS = ("lot-wise-stock-ageing", "stock-ageing")


class TestDeskBackgroundReports(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		clear_web_report_cache()
		self.jobs = []

	def tearDown(self):
		for job_name in self.jobs:
			for file_name in frappe.get_all(
				"File",
				filters={"attached_to_doctype": "YRP Report Job", "attached_to_name": job_name},
				pluck="name",
			):
				frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)
			frappe.delete_doc("YRP Report Job", job_name, ignore_permissions=True, force=True)
		frappe.db.commit()
		clear_web_report_cache()

	def test_long_or_open_ranges_move_to_background(self):
		for key, days in RANGE_REPORTS.items():
			entry = get_web_report(key)
			with self.subTest(report=key):
				self.assertFalse(needs_background(entry, {"from_date": "2099-01-01", "to_date": frappe.utils.add_days("2099-01-01", days)}))
				self.assertTrue(needs_background(entry, {"from_date": "2099-01-01", "to_date": frappe.utils.add_days("2099-01-01", days + 1)}))
				self.assertTrue(needs_background(entry, {"from_date": "", "to_date": "2099-01-01"}))
		for key in ALWAYS_REPORTS:
			self.assertTrue(needs_background(get_web_report(key), {"to_date": "2099-01-01"}))

	def test_background_desk_reports_complete_with_their_link_columns_stamped(self):
		requests = {key: {"from_date": "2099-01-01", "to_date": "2100-06-30"} for key in RANGE_REPORTS}
		requests.update({key: {"to_date": "2099-01-01", "item": "_Test Missing Ageing Item", "range1": 30, "range2": 60, "range3": 90} for key in ALWAYS_REPORTS})
		for key, filters in requests.items():
			with self.subTest(report=key):
				with (
					patch("yrp.web_reports.jobs.frappe.enqueue"),
					patch("yrp.web_reports.jobs.get_workers", return_value=[object()]),
				):
					queued = run_web_report(key, filters, refresh=1)
				self.assertEqual(queued["mode"], "background")
				self.jobs.append(queued["job"]["name"])
				with patch("yrp.web_reports.jobs.frappe.publish_realtime"):
					execute_report_job(queued["job"]["name"])
				stored = get_report_job(key, queued["job"]["name"], include_result=1)
				error = frappe.db.get_value("YRP Report Job", queued["job"]["name"], "error_message")
				self.assertEqual(stored["job"]["status"], "Completed", error)
				self.assertTrue(stored["columns"])
