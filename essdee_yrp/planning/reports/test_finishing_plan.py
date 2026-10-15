from frappe.tests import IntegrationTestCase

from essdee_yrp.planning.reports.report_test_support import PlanningReportLiveChecks


class TestPlanningFinishingPlanLive(PlanningReportLiveChecks, IntegrationTestCase):
	report_key = "finishing-plan"
	filters = {}
	expected_column = "lot"
