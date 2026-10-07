"""Shared guards and serializers for Cut Panel Store browser services."""

from __future__ import annotations

import frappe
from frappe import _


def parse_json_object(value, *, label: str = "Values") -> dict:
	"""Return a browser payload as an object and reject every other shape."""

	if isinstance(value, str):
		value = frappe.parse_json(value)
	if value is None:
		return {}
	if not isinstance(value, dict):
		frappe.throw(_("{0} must be an object.").format(label))
	return value


def assert_expected_modified(doc, expected_modified: str | None) -> None:
	"""Prevent a browser edit from silently replacing a newer document."""

	if expected_modified and str(doc.modified) != str(expected_modified):
		frappe.throw(
			_("This document changed after you opened it. Reload it and try again."),
			frappe.TimestampMismatchError,
		)
