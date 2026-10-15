from unittest import TestCase
from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.report.sd_yrp_work_order_pending_report import (
	sd_yrp_work_order_pending_report as report,
)
from essdee_yrp.planning.reports.report_test_support import PlanningReportLiveChecks


class TestPlanningWorkOrderPending(TestCase):
	def test_desk_summary_totals(self):
		rows = [
			{"delivered_qty": 10, "received_qty": 8, "pending_quantity": 2},
			{"delivered_qty": 3.5, "received_qty": 4, "pending_quantity": -0.5},
		]
		self.assertEqual([metric["value"] for metric in report.get_report_summary(rows)], [2, 13.5, 12, 1.5])
		self.assertEqual([metric["value"] for metric in report.get_report_summary([])], [0, 0, 0, 0])

	def test_desk_execute_keeps_filters_and_summary(self):
		filters = {key: [key + "-1"] for key in ("production_order", "lot", "item", "item_variant", "process", "supplier")}
		filters.update(from_date="2026-10-01", to_date="2026-10-15", status="Close Request")
		with patch.object(report, "get_work_order_pending_report", return_value=[]) as runner:
			result = report.execute(filters)
		runner.assert_called_once_with(**filters)
		self.assertEqual(len(result[0]), 10)
		self.assertEqual(result[4][0]["value"], 0)


class TestPlanningWorkOrderPendingLive(PlanningReportLiveChecks, IntegrationTestCase):
	report_key = "planning-work-order-pending"
	filters = {"from_date": "1900-01-01", "to_date": "1900-01-01"}
	expected_column = "pending_quantity"
