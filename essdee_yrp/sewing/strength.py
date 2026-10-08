"""Read-only HR worker-strength integration for the Sewing Details workbench."""

import frappe
import requests

HR_WORKERS_STRENGTH_REPORT_PATH = "/api/method/frappe.desk.query_report.run"
HR_WORKERS_STRENGTH_REPORT_NAME = "Workers Strength Report"
HR_EMPLOYEE_FIRST_PUNCHES_PATH = (
	"/api/method/essdee_attendance.essdee_attendance.report."
	"workers_strength_report.workers_strength_report.get_active_employee_first_punches"
)


def _invalid_response(phase, reason):
	# Log the failure category, never credentials, raw HR content or employee data.
	frappe.log_error(title=f"Invalid HR {phase} response", message=reason)
	if phase == "report":
		frappe.throw(
			"HR returned an invalid Workers Strength Report response. Please contact your administrator.",
			title="Invalid HR strength response",
		)
	frappe.throw(
		"HR returned an invalid employee first punch response. Please contact your administrator.",
		title="Invalid HR punch response",
	)


def _fetch_hr_payload(url, headers, params, phase):
	try:
		response = requests.get(url, headers=headers, params=params, timeout=30)
		response.raise_for_status()
	except requests.RequestException as error:
		status = getattr(error.response, "status_code", None)
		frappe.log_error(
			title=f"HR {phase} request failed",
			message=f"Failure: {type(error).__name__}; HTTP status: {status or 'unavailable'}",
		)
		if isinstance(error, requests.Timeout):
			frappe.throw("The HR connection timed out. Please try again.", title="HR connection timed out")
		if status in (401, 403):
			frappe.throw(
				"HR rejected the API credentials. Ask your administrator to check the HR integration settings.",
				title="HR authentication failed",
			)
		frappe.throw(
			"Unable to connect to HR or complete the request. Please try again or contact your administrator.",
			title="HR request failed",
		)
	# ValueError is a known decode failure only here, not around requests or business code.
	try:
		return response.json()
	except ValueError:
		_invalid_response(phase, "Response is not valid JSON")


@frappe.whitelist()
def get_worker_strength_report(report_date, from_time, to_time):
	frappe.has_permission("SD YRP Sewing Plan", "read", throw=True)
	if not report_date:
		frappe.throw("Date is mandatory", title="Date required")
	if not from_time:
		frappe.throw("From Time is mandatory", title="From Time required")
	if not to_time:
		frappe.throw("To Time is mandatory", title="To Time required")

	settings = frappe.get_single("SD YRP MRP Settings")
	hr_site_url = (settings.get("hr_site_url") or "").strip().rstrip("/")
	api_key = (settings.get("hr_api_key") or "").strip()
	api_secret = settings.get_password("hr_api_secret") if settings.get("hr_api_secret") else None
	if not hr_site_url:
		frappe.throw("Configure the HR Site URL in MRP Settings", title="HR configuration required")
	if not api_key or not api_secret:
		frappe.throw(
			"Configure the HR API Key and HR API Secret Key in MRP Settings",
			title="HR configuration required",
		)

	shifts = []
	for row in settings.get("hr_shifts") or []:
		shift_type = (row.get("shift_type") or "").strip()
		if shift_type and shift_type not in shifts:
			shifts.append(shift_type)
	if not shifts:
		frappe.throw("Add at least one Shift to Fetch in MRP Settings", title="HR configuration required")

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
	payload = _fetch_hr_payload(
		f"{hr_site_url}{HR_WORKERS_STRENGTH_REPORT_PATH}", headers, request_args, "report"
	)

	report_data = payload.get("message") if isinstance(payload, dict) else None
	if not isinstance(report_data, dict):
		_invalid_response("report", "Expected a report message object")
	columns = report_data.get("columns")
	rows = report_data.get("result")
	if (
		not isinstance(columns, list)
		or not all(
			isinstance(column, dict)
			and isinstance(column.get("fieldname"), str)
			and column["fieldname"]
			for column in columns
		)
		or not isinstance(rows, list)
		or not all(isinstance(row, (dict, list)) for row in rows)
	):
		_invalid_response("report", "Expected report column definitions and object or array rows")

	punch_payload = _fetch_hr_payload(
		f"{hr_site_url}{HR_EMPLOYEE_FIRST_PUNCHES_PATH}",
		headers,
		{
			"report_date": report_date,
			"from_time": from_time,
			"to_time": to_time,
			"shift_type": frappe.as_json(shifts),
		},
		"punch",
	)

	punch_data = punch_payload.get("message") if isinstance(punch_payload, dict) else None
	employee_punches = punch_data.get("rows") if isinstance(punch_data, dict) else None
	if not isinstance(employee_punches, list) or not all(isinstance(row, dict) for row in employee_punches):
		_invalid_response("punch", "Expected employee punch row objects")

	return {
		"columns": columns,
		"rows": rows,
		"employee_punches": employee_punches,
		"shifts": shifts,
		"add_total_row": report_data.get("add_total_row", 0),
	}
