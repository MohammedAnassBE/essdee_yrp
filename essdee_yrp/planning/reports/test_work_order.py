from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.report.sd_yrp_work_order_report import sd_yrp_work_order_report as report
from essdee_yrp.planning.reports.report_test_support import PlanningReportLiveChecks


class TestPlanningWorkOrder(TestCase):
	def test_dynamic_received_columns_keep_desk_order(self):
		columns = report.get_columns(["Accepted", "Rework"])
		names = [column["fieldname"] for column in columns]
		self.assertEqual(names[12:16], ["Accepted", "Rework", "others", "pending"])
		self.assertEqual(names[-4:], ["first_dc_date", "last_dc_date", "first_grn_date", "last_grn_date"])

	def test_empty_settings_error_is_not_swallowed(self):
		with patch.object(frappe.db, "get_single_value", return_value=None):
			with self.assertRaises(AttributeError):
				report.execute({"based_on": "WO Status"})


class TestPlanningWorkOrderLive(PlanningReportLiveChecks, IntegrationTestCase):
	report_key = "planning-work-order"
	filters = {"based_on": "Date", "from_date": "1900-01-01", "to_date": "1900-01-01"}
	expected_column = "work_order"

	def setUp(self):
		super().setUp()
		self.previous_types = frappe.db.get_single_value("SD YRP MRP Settings", "received_type_list")
		frappe.db.set_single_value("SD YRP MRP Settings", "received_type_list", "Accepted,Rework")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.set_single_value("SD YRP MRP Settings", "received_type_list", self.previous_types)
		super().tearDown()
