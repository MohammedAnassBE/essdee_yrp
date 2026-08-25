"""Read-only HR worker-strength integration for the Sewing Details workbench."""

import frappe
import requests


HR_WORKERS_STRENGTH_REPORT_PATH = "/api/method/frappe.desk.query_report.run"
HR_WORKERS_STRENGTH_REPORT_NAME = "Workers Strength Report"
HR_EMPLOYEE_FIRST_PUNCHES_PATH = (
	"/api/method/essdee_attendance.essdee_attendance.report."
	"workers_strength_report.workers_strength_report.get_active_employee_first_punches"
)


@frappe.whitelist()
def get_worker_strength_report(report_date, from_time, to_time):
	frappe.has_permission("Sewing Plan", "read", throw=True)
	if not report_date:
		frappe.throw("Date is mandatory")
	if not from_time:
		frappe.throw("From Time is mandatory")
	if not to_time:
		frappe.throw("To Time is mandatory")

	settings = frappe.get_single("MRP Settings")
	hr_site_url = (settings.get("hr_site_url") or "").strip().rstrip("/")
	api_key = (settings.get("hr_api_key") or "").strip()
	api_secret = (
		settings.get_password("hr_api_secret")
		if settings.get("hr_api_secret")
		else None
	)
	if not hr_site_url:
		frappe.throw("Configure the HR Site URL in MRP Settings")
	if not api_key or not api_secret:
		frappe.throw("Configure the HR API Key and HR API Secret Key in MRP Settings")

	shifts = []
	for row in settings.get("hr_shifts") or []:
		shift_type = (row.get("shift_type") or "").strip()
		if shift_type and shift_type not in shifts:
			shifts.append(shift_type)
	if not shifts:
		frappe.throw("Add at least one Shift to Fetch in MRP Settings")

	filters = {
		"report_date": report_date,
		"from_time": from_time,
		"to_time": to_time,
		"shift_type": shifts,
		"department_wise": 0,
		"manpower_agent_wise": 0,
	}
	request_args = {
		"report_name": HR_WORKERS_STRENGTH_REPORT_NAME,
		"filters": frappe.as_json(filters),
		"ignore_prepared_report": 1,
		"are_default_filters": 0,
	}
	headers = {
		"Accept": "application/json",
		"Authorization": f"token {api_key}:{api_secret}",
	}
	try:
		response = requests.get(
			f"{hr_site_url}{HR_WORKERS_STRENGTH_REPORT_PATH}",
			headers=headers,
			params=request_args,
			timeout=30,
		)
		response.raise_for_status()
		payload = response.json()
	except requests.RequestException:
		frappe.log_error(frappe.get_traceback(), "HR Workers Strength Report API Error")
		frappe.throw(
			"Unable to fetch the Workers Strength Report from HR. "
			"Verify the HR API credentials and try again."
		)
	except ValueError:
		frappe.log_error(
			frappe.get_traceback(), "Invalid HR Workers Strength Report Response"
		)
		frappe.throw("HR returned an invalid Workers Strength Report response")

	report_data = payload.get("message") if isinstance(payload, dict) else None
	if not isinstance(report_data, dict):
		frappe.throw("HR returned an invalid Workers Strength Report response")
	columns = report_data.get("columns")
	rows = report_data.get("result")
	if not isinstance(columns, list) or not isinstance(rows, list):
		frappe.throw("HR returned an invalid Workers Strength Report response")

	try:
		punch_response = requests.get(
			f"{hr_site_url}{HR_EMPLOYEE_FIRST_PUNCHES_PATH}",
			headers=headers,
			params={
				"report_date": report_date,
				"from_time": from_time,
				"to_time": to_time,
				"shift_type": frappe.as_json(shifts),
			},
			timeout=30,
		)
		punch_response.raise_for_status()
		punch_payload = punch_response.json()
	except requests.RequestException:
		frappe.log_error(frappe.get_traceback(), "HR Employee First Punch API Error")
		frappe.throw(
			"Unable to fetch employee first punches from HR. "
			"Verify the HR API credentials and try again."
		)
	except ValueError:
		frappe.log_error(
			frappe.get_traceback(), "Invalid HR Employee First Punch Response"
		)
		frappe.throw("HR returned an invalid employee first punch response")

	punch_data = punch_payload.get("message") if isinstance(punch_payload, dict) else None
	employee_punches = punch_data.get("rows") if isinstance(punch_data, dict) else None
	if not isinstance(employee_punches, list):
		frappe.throw("HR returned an invalid employee first punch response")

	return {
		"columns": columns,
		"rows": rows,
		"employee_punches": employee_punches,
		"shifts": shifts,
		"add_total_row": report_data.get("add_total_row", 0),
	}
