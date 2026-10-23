import frappe
from frappe import _
from frappe.auth import validate_auth_via_hooks
from frappe.handler import execute_cmd

COUNT_METHOD = "frappe.desk.reportview.get_count"
MAX_FILTER_SETS = 100


@frappe.whitelist()
@frappe.read_only()
def get_counts(doctype: str, filter_sets: list | str, distinct: bool | None = None) -> list:
	"""Return `get_count` for each filter set, as if each were its own `/api/method` call."""
	filter_sets = frappe.parse_json(filter_sets)
	if not isinstance(filter_sets, list):
		frappe.throw(_("Filter sets must be a list."))
	if len(filter_sets) > MAX_FILTER_SETS:
		frappe.throw(_("At most {0} filter sets can be counted at once.").format(MAX_FILTER_SETS))
	return [get_count_as_request(doctype, filters, distinct) for filters in filter_sets]


def get_count_as_request(doctype, filters, distinct=None):
	"""Run the request auth hooks and `get_count` dispatch (overrides, API scripts, whitelist) on its own form_dict."""
	form_dict = frappe._dict(cmd=COUNT_METHOD, doctype=doctype, filters=filters)
	if distinct is not None:
		form_dict.distinct = distinct
	previous = frappe.local.form_dict
	previous_message = frappe.response.pop("message", None)
	frappe.local.form_dict = form_dict
	try:
		validate_auth_via_hooks()
		data = execute_cmd(COUNT_METHOD)
		# API Server Scripts may answer through frappe.response, like frappe.handler.handle reads it.
		return data if data is not None else frappe.response.get("message")
	finally:
		frappe.local.form_dict = previous
		frappe.response.pop("message", None)
		if previous_message is not None:
			frappe.response["message"] = previous_message
