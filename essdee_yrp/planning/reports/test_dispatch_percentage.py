from unittest import TestCase
from unittest.mock import patch

from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.report.sd_yrp_dispatch_percentage_report import (
	sd_yrp_dispatch_percentage_report as report,
)
from essdee_yrp.planning.reports.report_test_support import PlanningReportLiveChecks


class TestPlanningDispatchPercentage(TestCase):
	def test_desk_filters_and_columns_are_preserved(self):
		rows = [{"date": "2026-10-01", "lot": "LOT-1", "percentage": 80}]
		with patch.object(report, "get_dispatch_percentage_report", return_value=rows) as runner:
			columns, result = report.execute({"percentage": 75, "lot": ["LOT-1"], "item": ["ITEM-1"]})
		runner.assert_called_once_with(75, ["LOT-1"], ["ITEM-1"])
		self.assertEqual(result, rows)
		self.assertEqual([column["fieldname"] for column in columns], ["date", "lot", "stock_entry", "item", "percentage"])


class TestPlanningDispatchPercentageLive(PlanningReportLiveChecks, IntegrationTestCase):
	report_key = "planning-dispatch-percentage"
	filters = {"percentage": 75}
	expected_column = "percentage"
