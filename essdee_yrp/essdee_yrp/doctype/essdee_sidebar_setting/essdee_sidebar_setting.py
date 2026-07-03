# Copyright (c) 2026, anas@essdee.fit and contributors
# For license information, please see license.txt

import hashlib

from frappe.model.document import Document


class EssdeeSidebarSetting(Document):
	"""Per-user, server-side store for SPA left-sidebar collapse state.

	One row per user holds the list of sidebar group/section names that user
	has collapsed. The whitelisted API in essdee_yrp.api.sidebar_view owns all
	reads/writes and always scopes to frappe.session.user, so the SPA persists
	section collapse choices across server restarts and across
	browsers/devices (mirrors the per-user "Essdee Child Table View Setting"
	pattern).
	"""

	def autoname(self):
		"""Deterministic name from the user (one row per user).

		The user uniquely identifies a row, so deriving the name from it makes
		two near-simultaneous inserts for the SAME user collide on the primary
		key (DuplicateEntryError) instead of silently creating duplicate rows —
		the API's set_collapsed catches that collision and falls back to
		updating the existing row.

		Uses a sha1 hex digest (truncated to 20 chars) so the name is a stable,
		collision-resistant, filesystem/URL-safe ASCII id rather than exposing
		the raw user email in the document name.
		"""
		self.name = hashlib.sha1((self.user or "").encode("utf-8")).hexdigest()[:20]
