from unittest import TestCase
from unittest.mock import patch

from essdee_yrp.planning import web_workspace


class TestPlanningReportsSection(TestCase):
	def production(self, multi_ccr, ppo):
		with (
			patch.object(web_workspace, "can_run_desk_report", return_value=False),
			patch.object(web_workspace.cutting_reports, "get_report_permissions", return_value={"multi-ccr": multi_ccr}),
			patch("essdee_yrp.planning.reports.production_quantities.can_read", return_value=False),
			patch.object(web_workspace.frappe, "has_permission", side_effect=lambda doctype, ptype: doctype == "YRP Production Order" and ppo),
		):
			return web_workspace._reports_section({}, {})["production"]

	def test_multi_ccr_and_ppo_follow_source_access(self):
		self.assertEqual(self.production(True, True), {
			"multi_ccr": {"label": "Multi CCR", "can_read": True},
			"ppo_report": {"label": "PPO Report", "can_read": True, "can_export": True},
		})
		self.assertEqual(self.production(False, False), {})
