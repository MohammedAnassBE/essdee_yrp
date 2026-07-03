# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import hashlib

from frappe.model.document import Document


class EssdeeChildTableViewSetting(Document):
	"""Per-user, server-side store for SPA child-table column settings.

	One row per (user, parent_doctype, child_table) holds which columns are
	visible and per-column pixel widths for that user's grid. The whitelisted
	API in essdee_yrp.api.child_table_view owns all reads/writes and always
	scopes to frappe.session.user, so the SPA persists column choices across
	server restarts and across browsers/devices (like Frappe's List View
	per-user settings).
	"""

	def autoname(self):
		"""Deterministic name from (user, parent_doctype, child_table).

		The triple uniquely identifies a row, so deriving the name from it makes
		two near-simultaneous inserts for the SAME triple collide on the primary
		key (DuplicateEntryError) instead of silently creating duplicate rows —
		the API's save_view catches that collision and falls back to updating the
		existing row.

		Uses a sha1 hex digest (truncated to 20 chars) so the name is a stable,
		collision-resistant, filesystem/URL-safe ASCII id rather than exposing
		the raw user email in the document name.
		"""
		raw = f"{self.user}|{self.parent_doctype}|{self.child_table}"
		self.name = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]
