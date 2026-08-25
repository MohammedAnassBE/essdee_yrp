from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.sewing import strength


class FakeHRSettings:
	def __init__(
		self,
		site_url="https://hr.essdee.fit/",
		api_key="hr-key",
		api_secret="hr-secret",
		shifts=None,
	):
		self.values = {
			"hr_site_url": site_url,
			"hr_api_key": api_key,
			"hr_api_secret": api_secret,
			"hr_shifts": [
				frappe._dict(shift_type=shift_type)
				for shift_type in (shifts if shifts is not None else ["Shift A"])
			],
		}
		self.api_secret = api_secret

	def get(self, fieldname):
		return self.values.get(fieldname)

	def get_password(self, fieldname):
		return self.api_secret if fieldname == "hr_api_secret" else None


class TestSewingWorkerStrength(FrappeTestCase):
	def test_report_requires_sewing_plan_read_permission(self):
		with (
			patch.object(
				strength.frappe,
				"has_permission",
				side_effect=frappe.PermissionError,
			),
			patch.object(strength.frappe, "get_single") as get_single,
		):
			with self.assertRaises(frappe.PermissionError):
				strength.get_worker_strength_report(
					"2026-08-25", "08:00:00", "17:00:00"
				)

		get_single.assert_not_called()

	def test_report_uses_hr_credentials_and_unique_configured_shifts(self):
		settings = FakeHRSettings(shifts=["Shift A", " Shift B ", "Shift A"])
		report_response = MagicMock()
		report_response.json.return_value = {
			"message": {
				"columns": [
					{
						"fieldname": "department",
						"label": "Department",
						"fieldtype": "Data",
					},
					{"fieldname": "strength", "label": "Strength", "fieldtype": "Int"},
				],
				"result": [{"department": "Sewing", "strength": 12}],
				"add_total_row": 1,
			}
		}
		punch_response = MagicMock()
		punch_response.json.return_value = {
			"message": {
				"rows": [
					{
						"employee": "EMP-001",
						"employee_name": "Test Employee",
						"shift_type": "Shift A",
						"first_punch": "08:05:00",
					}
				]
			}
		}

		with (
			patch.object(strength.frappe, "get_single", return_value=settings),
			patch.object(
				strength.requests,
				"get",
				side_effect=[report_response, punch_response],
			) as mock_get,
		):
			result = strength.get_worker_strength_report(
				"2026-08-25", "08:00:00", "17:00:00"
			)

		self.assertEqual(mock_get.call_count, 2)
		request = mock_get.call_args_list[0]
		self.assertEqual(
			request.args[0],
			"https://hr.essdee.fit/api/method/frappe.desk.query_report.run",
		)
		self.assertEqual(
			request.kwargs["headers"]["Authorization"], "token hr-key:hr-secret"
		)
		filters = frappe.parse_json(request.kwargs["params"]["filters"])
		self.assertEqual(filters["shift_type"], ["Shift A", "Shift B"])
		self.assertEqual(result["rows"], [{"department": "Sewing", "strength": 12}])
		self.assertEqual(result["employee_punches"][0]["first_punch"], "08:05:00")
		self.assertEqual(result["shifts"], ["Shift A", "Shift B"])

	def test_report_requires_hr_credentials(self):
		settings = FakeHRSettings(api_key="", api_secret="")
		with patch.object(strength.frappe, "get_single", return_value=settings):
			with self.assertRaisesRegex(frappe.ValidationError, "Configure the HR API"):
				strength.get_worker_strength_report(
					"2026-08-25", "08:00:00", "17:00:00"
				)

	def test_report_requires_hr_site_url(self):
		with patch.object(
			strength.frappe, "get_single", return_value=FakeHRSettings(site_url="")
		):
			with self.assertRaisesRegex(frappe.ValidationError, "HR Site URL"):
				strength.get_worker_strength_report(
					"2026-08-25", "08:00:00", "17:00:00"
				)

	def test_report_requires_configured_shifts(self):
		with patch.object(
			strength.frappe, "get_single", return_value=FakeHRSettings(shifts=[])
		):
			with self.assertRaisesRegex(frappe.ValidationError, "at least one Shift"):
				strength.get_worker_strength_report(
					"2026-08-25", "08:00:00", "17:00:00"
				)

	def test_report_rejects_invalid_hr_response(self):
		response = MagicMock()
		response.json.return_value = {"message": {"columns": []}}
		with (
			patch.object(
				strength.frappe, "get_single", return_value=FakeHRSettings()
			),
			patch.object(strength.requests, "get", return_value=response),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "invalid Workers Strength"):
				strength.get_worker_strength_report(
					"2026-08-25", "08:00:00", "17:00:00"
				)

	def test_report_rejects_invalid_first_punch_response(self):
		report_response = MagicMock()
		report_response.json.return_value = {
			"message": {"columns": [], "result": [], "add_total_row": 0}
		}
		punch_response = MagicMock()
		punch_response.json.return_value = {"message": {"rows": None}}
		with (
			patch.object(
				strength.frappe, "get_single", return_value=FakeHRSettings()
			),
			patch.object(
				strength.requests,
				"get",
				side_effect=[report_response, punch_response],
			),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "first punch"):
				strength.get_worker_strength_report(
					"2026-08-25", "08:00:00", "17:00:00"
				)
