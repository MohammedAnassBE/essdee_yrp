from unittest.mock import MagicMock, patch

import frappe
import requests
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
	def test_missing_inputs_have_specific_business_titles_without_hr_requests(self):
		for args, field in [
			(("", "08:00:00", "17:00:00"), "Date"),
			(("2026-10-08", "", "17:00:00"), "From Time"),
			(("2026-10-08", "08:00:00", ""), "To Time"),
		]:
			with self.subTest(field=field), patch.object(strength.requests, "get") as request:
				frappe.clear_messages()
				with self.assertRaisesRegex(frappe.ValidationError, field):
					strength.get_worker_strength_report(*args)
				self.assertEqual(frappe.message_log[-1].title, f"{field} required")
				request.assert_not_called()

	def test_upstream_failures_are_distinct_safe_logged_business_errors(self):
		# Wrong exception ordering would turn timeouts/authentication into a generic request error.
		for phase in ["report", "punch"]:
			for exception, title, message in [
				(requests.Timeout("private upstream hr-secret"), "HR connection timed out", "timed out"),
				(
					requests.HTTPError("private upstream hr-secret", response=MagicMock(status_code=401)),
					"HR authentication failed", "credentials",
				),
				(
					requests.HTTPError("private upstream hr-secret", response=MagicMock(status_code=403)),
					"HR authentication failed", "credentials",
				),
				(requests.ConnectionError("private upstream hr-secret"), "HR request failed", "connect"),
				(
					requests.HTTPError("private upstream hr-secret", response=MagicMock(status_code=500)),
					"HR request failed", "request",
				),
			]:
				with self.subTest(phase=phase, exception=title):
					responses = [exception] if phase == "report" else [self.report_response(), exception]
					with (
						patch.object(strength.frappe, "get_single", return_value=FakeHRSettings()),
						patch.object(strength.requests, "get", side_effect=responses),
						patch.object(strength.frappe, "log_error") as log,
					):
						frappe.clear_messages()
						with self.assertRaisesRegex(frappe.ValidationError, message) as raised:
							strength.get_worker_strength_report("2026-10-08", "08:00:00", "17:00:00")
						self.assertEqual(frappe.message_log[-1].title, title)
						self.assertNotIn("private upstream", str(raised.exception))
						self.assertNotIn("hr-secret", str(raised.exception))
						log.assert_called_once()
						self.assertIn(phase, str(log.call_args).lower())
						self.assertNotIn("hr-secret", str(log.call_args))

	def report_response(self):
		response = MagicMock()
		response.json.return_value = {"message": {"columns": [], "result": [], "add_total_row": 0}}
		return response

	def test_invalid_payloads_are_distinct_and_logged_including_decode_errors(self):
		for phase, payloads, title in [
			(
				"report",
				[
					None, {"message": {"columns": [], "result": None}},
					{"message": {"columns": [None], "result": []}},
					{"message": {"columns": [], "result": [None]}},
					ValueError("raw hr-secret response"),
				],
				"Invalid HR strength response",
			),
			(
				"punch",
				[None, {"message": {"rows": None}}, {"message": {"rows": [None]}}, ValueError("raw hr-secret response")],
				"Invalid HR punch response",
			),
		]:
			for payload in payloads:
				with self.subTest(phase=phase, payload=payload):
					response = MagicMock()
					if isinstance(payload, Exception):
						response.json.side_effect = payload
					else:
						response.json.return_value = payload
					valid_punch = MagicMock()
					valid_punch.json.return_value = {"message": {"rows": []}}
					responses = (
						[response, valid_punch] if phase == "report" else [self.report_response(), response]
					)
					with (
						patch.object(strength.frappe, "get_single", return_value=FakeHRSettings()),
						patch.object(strength.requests, "get", side_effect=responses),
						patch.object(strength.frappe, "log_error") as log,
					):
						frappe.clear_messages()
						with self.assertRaises(frappe.ValidationError) as raised:
							strength.get_worker_strength_report("2026-10-08", "08:00:00", "17:00:00")
						self.assertEqual(frappe.message_log[-1].title, title)
						self.assertNotIn("hr-secret", str(raised.exception))
						log.assert_called_once()

	def test_unknown_programming_errors_propagate_without_business_normalization(self):
		for exception in [RuntimeError("programming bug"), ValueError("programming bug")]:
			with (
				self.subTest(exception=type(exception).__name__),
				patch.object(strength.frappe, "get_single", return_value=FakeHRSettings()),
				patch.object(strength.requests, "get", side_effect=exception),
				patch.object(strength.frappe, "log_error") as log,
			):
				with self.assertRaises(type(exception)) as raised:
					strength.get_worker_strength_report("2026-10-08", "08:00:00", "17:00:00")
				self.assertIs(raised.exception, exception)
				log.assert_not_called()

	def test_valid_empty_report_is_not_an_hr_error(self):
		punch_response = MagicMock()
		punch_response.json.return_value = {"message": {"rows": []}}
		with (
			patch.object(strength.frappe, "get_single", return_value=FakeHRSettings()),
			patch.object(strength.requests, "get", side_effect=[self.report_response(), punch_response]),
			patch.object(strength.frappe, "log_error") as log,
		):
			result = strength.get_worker_strength_report("2026-10-08", "08:00:00", "17:00:00")
		self.assertEqual(
			result,
			{"columns": [], "rows": [], "employee_punches": [], "shifts": ["Shift A"], "add_total_row": 0},
		)
		log.assert_not_called()

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
				strength.get_worker_strength_report("2026-08-25", "08:00:00", "17:00:00")

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
			result = strength.get_worker_strength_report("2026-08-25", "08:00:00", "17:00:00")

		self.assertEqual(mock_get.call_count, 2)
		request = mock_get.call_args_list[0]
		self.assertEqual(
			request.args[0],
			"https://hr.essdee.fit/api/method/frappe.desk.query_report.run",
		)
		self.assertEqual(request.kwargs["headers"]["Authorization"], "token hr-key:hr-secret")
		filters = frappe.parse_json(request.kwargs["params"]["filters"])
		self.assertEqual(filters["shift_type"], ["Shift A", "Shift B"])
		self.assertEqual(result["rows"], [{"department": "Sewing", "strength": 12}])
		self.assertEqual(result["employee_punches"][0]["first_punch"], "08:05:00")
		self.assertEqual(result["shifts"], ["Shift A", "Shift B"])

	def test_report_requires_hr_credentials(self):
		settings = FakeHRSettings(api_key="", api_secret="")
		with patch.object(strength.frappe, "get_single", return_value=settings):
			with self.assertRaisesRegex(frappe.ValidationError, "Configure the HR API"):
				strength.get_worker_strength_report("2026-08-25", "08:00:00", "17:00:00")

	def test_report_requires_hr_site_url(self):
		with patch.object(strength.frappe, "get_single", return_value=FakeHRSettings(site_url="")):
			with self.assertRaisesRegex(frappe.ValidationError, "HR Site URL"):
				strength.get_worker_strength_report("2026-08-25", "08:00:00", "17:00:00")

	def test_report_requires_configured_shifts(self):
		with patch.object(strength.frappe, "get_single", return_value=FakeHRSettings(shifts=[])):
			with self.assertRaisesRegex(frappe.ValidationError, "at least one Shift"):
				strength.get_worker_strength_report("2026-08-25", "08:00:00", "17:00:00")

	def test_report_rejects_invalid_hr_response(self):
		response = MagicMock()
		response.json.return_value = {"message": {"columns": []}}
		with (
			patch.object(strength.frappe, "get_single", return_value=FakeHRSettings()),
			patch.object(strength.requests, "get", return_value=response),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "invalid Workers Strength"):
				strength.get_worker_strength_report("2026-08-25", "08:00:00", "17:00:00")

	def test_report_rejects_invalid_first_punch_response(self):
		report_response = MagicMock()
		report_response.json.return_value = {"message": {"columns": [], "result": [], "add_total_row": 0}}
		punch_response = MagicMock()
		punch_response.json.return_value = {"message": {"rows": None}}
		with (
			patch.object(strength.frappe, "get_single", return_value=FakeHRSettings()),
			patch.object(
				strength.requests,
				"get",
				side_effect=[report_response, punch_response],
			),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "first punch"):
				strength.get_worker_strength_report("2026-08-25", "08:00:00", "17:00:00")
