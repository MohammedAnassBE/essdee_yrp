"""Safe readers for historical Finishing JSON payloads."""

from __future__ import annotations

import frappe


def json_object(value, *, max_depth: int = 3) -> dict:
	"""Return a JSON object, including legacy values encoded more than once.

	Production API contains historical ``set_combination`` rows whose database
	value is a JSON string containing another JSON object string.  Frappe's
	normal parser intentionally decodes one layer only, so business logic that
	uses ``.items()`` or ``.get()`` must unwrap the legacy representation first.
	Invalid or non-object payloads are treated as an empty combination.
	"""

	for _index in range(max_depth):
		if not isinstance(value, str):
			break
		try:
			value = frappe.parse_json(value)
		except (TypeError, ValueError):
			return {}
	return value if isinstance(value, dict) else {}
