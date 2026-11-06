from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.planning import dashboard_workspace


class TestDashboardEndpointAccess(TestCase):
	def test_every_endpoint_requires_dashboard_read(self):
		calls = (
			lambda: dashboard_workspace.get_dashboard(),
			lambda: dashboard_workspace.get_tracking_options(),
			lambda: dashboard_workspace.get_tracking(["PPO-00044"], []),
			lambda: dashboard_workspace.get_process_detail("F0426-85", "Cutting"),
		)
		with patch.object(dashboard_workspace, "can_read", return_value=False):
			for call in calls:
				with self.assertRaises(frappe.PermissionError):
					call()

	def test_tracking_needs_a_ppo_or_lot(self):
		with patch.object(dashboard_workspace, "can_read", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				dashboard_workspace.get_tracking([], [])

	def test_dashboard_needs_finishing_plan_read_for_dispatch(self):
		with patch.object(
			dashboard_workspace.frappe,
			"has_permission",
			side_effect=lambda doctype, ptype: doctype != "SD YRP Finishing Plan",
		):
			self.assertFalse(dashboard_workspace.has_dashboard_access())
