"""Read-only Desk boot compatibility for the host application."""

import json

from frappe.core.doctype.session_default_settings.session_default_settings import (
	get_session_default_values,
)


def boot_session(bootinfo):
	"""Provide real user defaults before Frappe's sidebar evaluates its menu.

	The toolbar fetches these asynchronously too, but SidebarHeader can run
	first and access ``session_defaults.length`` while it is still undefined.
	Use Frappe's own user-scoped reader; don't hide the menu or invent defaults.
	"""
	if isinstance(bootinfo.get("session_defaults"), list):
		return
	fields = json.loads(get_session_default_values())
	if not isinstance(fields, list):
		raise ValueError("Session default fields must be a list")
	bootinfo["session_defaults"] = fields
