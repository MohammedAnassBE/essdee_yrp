from collections.abc import Mapping
from contextlib import contextmanager

import frappe
from frappe import _


def parse_mapping(value, label: str) -> dict:
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except (TypeError, ValueError):
			frappe.throw(_("{0} is not valid JSON.").format(label))
	if not isinstance(value, Mapping):
		frappe.throw(_("{0} must be an object.").format(label))
	return dict(value)


def value(source, fieldname, default=None):
	if isinstance(source, Mapping):
		return source.get(fieldname, default)
	getter = getattr(source, "get", None)
	return getter(fieldname, default) if callable(getter) else getattr(source, fieldname, default)


def permission_flags(doctype: str, permission_types, doc=None) -> dict[str, bool]:
	return {
		f"can_{permission_type}": bool(
			frappe.has_permission(
				doctype,
				ptype=permission_type,
				doc=None if permission_type == "create" else doc,
			)
		)
		for permission_type in permission_types
	}


def action(allowed: bool, label: str, reason: str = "") -> dict:
	return {"allowed": bool(allowed), "label": label, "reason": "" if allowed else reason}


def assert_expected_modified(doc, expected_modified=None) -> None:
	if expected_modified is None or not str(expected_modified).strip():
		frappe.throw(_("Reload the record before making changes."), frappe.ValidationError)
	if str(doc.modified) != str(expected_modified):
		frappe.throw(
			_("{0} changed after you opened it. Refresh and try again.").format(doc.name),
			frappe.TimestampMismatchError,
		)


def is_masked_value(value) -> bool:
	return bool(value) and not str(value).strip().strip("Xx*")


@contextmanager
def report_access_scope():
	"""Answer each report access check once per user while one capability payload is built; nested scopes join the outer one."""
	if getattr(frappe.local, "report_access", None) is not None:
		yield
		return
	frappe.local.report_access = {}
	try:
		yield
	finally:
		frappe.local.report_access = None


def get_scoped_report_access(report_name: str, check) -> bool:
	"""`check(report_name)`, reused inside an open `report_access_scope`; outside one it always runs."""
	answers = getattr(frappe.local, "report_access", None)
	if answers is None:
		return check(report_name)
	key = (frappe.session.user, report_name)
	if key not in answers:
		answers[key] = check(report_name)
	return answers[key]
