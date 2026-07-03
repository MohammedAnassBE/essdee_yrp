"""Per-user, server-side store for SPA left-sidebar section collapse state.

The SPA's left sidebar groups DocType links into named SECTIONS (Procurement,
Production, Stock, …). Each user can collapse a section to hide its items; this
module persists which sections are collapsed server-side in the
"Essdee Sidebar Setting" DocType so the choice follows the user across server
restarts AND across browsers/devices.

Both endpoints are scoped to ``frappe.session.user`` — a user can never read or
write another user's row. The internal read/write uses ``ignore_permissions``
because normal SPA users have no role on the setting DocType (it is an internal
preference store, not user-facing data); per-user isolation is enforced here in
code, not via the doctype permission rules.

Mirrors the (user, parent_doctype, child_table) pattern in
``essdee_yrp.api.child_table_view`` — same one-row-per-key deterministic
autoname + savepoint-guarded upsert — but keyed by user alone (one row/user).
"""

import json

import frappe

SETTING_DOCTYPE = "Essdee Sidebar Setting"


def _parse_json_field(raw):
	"""Decode a stored Long Text JSON field; tolerate empty / malformed values."""
	if not raw:
		return None
	try:
		return json.loads(raw)
	except (ValueError, TypeError):
		return None


def _coerce_to_json_text(value):
	"""Normalise an incoming collapsed_sections value to a JSON-array text.

	Accepts either a JSON string (from the request body) or an already decoded
	list; anything that is not a list of strings is normalised to ``[]`` so the
	stored value is always a valid JSON array of section names.
	"""
	if isinstance(value, str):
		try:
			value = json.loads(value) if value.strip() else None
		except (ValueError, TypeError):
			value = None
	if not isinstance(value, list):
		value = []
	# Keep only non-empty string names, de-duplicated while preserving order.
	seen = set()
	clean = []
	for name in value:
		if isinstance(name, str) and name.strip() and name not in seen:
			seen.add(name)
			clean.append(name)
	return json.dumps(clean)


def _find_existing(user):
	"""Name of this user's settings row, or None."""
	return frappe.db.get_value(SETTING_DOCTYPE, {"user": user}, "name")


@frappe.whitelist()
def get_collapsed():
	"""Return the current user's collapsed sidebar sections.

	@returns {"collapsed_sections": <list of section names>} — an empty list
	  when the user has never collapsed anything.
	"""
	user = frappe.session.user
	name = _find_existing(user)
	if not name:
		return {"collapsed_sections": []}

	raw = frappe.db.get_value(SETTING_DOCTYPE, name, "collapsed_sections")
	parsed = _parse_json_field(raw)
	sections = [s for s in parsed if isinstance(s, str)] if isinstance(parsed, list) else []
	return {"collapsed_sections": sections}


@frappe.whitelist()
def set_collapsed(collapsed_sections=None):
	"""Upsert the current user's collapsed sidebar sections.

	collapsed_sections may arrive as a JSON string (from the request body) or as
	an already-decoded list; both are normalised to a JSON-array text and stored.
	The row is always keyed to ``frappe.session.user`` so a user can only ever
	write their own setting.

	@returns the saved value in the same shape as get_collapsed().
	"""
	user = frappe.session.user
	sections_text = _coerce_to_json_text(collapsed_sections)

	name = _find_existing(user)
	if name:
		# Fast path: row already exists for this user — update it in place.
		doc = frappe.get_doc(SETTING_DOCTYPE, name)
		doc.collapsed_sections = sections_text
		doc.save(ignore_permissions=True)
	else:
		# No row found. The insert may still race a concurrent save for the SAME
		# user (e.g. two tabs toggling at once): both can miss the find above. The
		# row is deterministically named from the user (see the controller's
		# autoname), so a concurrent insert collides on the primary key instead of
		# silently duplicating. We wrap the insert in a savepoint so that, on
		# collision, only the failed insert is rolled back (not the whole request
		# transaction); then we re-fetch the now-existing row and update it so this
		# save is not dropped.
		savepoint = "essdee_sidebar_insert"
		frappe.db.savepoint(savepoint)
		try:
			doc = frappe.get_doc(
				{
					"doctype": SETTING_DOCTYPE,
					"user": user,
					"collapsed_sections": sections_text,
				}
			)
			doc.insert(ignore_permissions=True)
		except frappe.exceptions.DuplicateEntryError:
			# Lost the race — the row now exists. Undo the failed insert, then
			# re-fetch by user and update it instead.
			frappe.db.rollback(save_point=savepoint)
			existing = _find_existing(user)
			if existing:
				doc = frappe.get_doc(SETTING_DOCTYPE, existing)
				doc.collapsed_sections = sections_text
				doc.save(ignore_permissions=True)

	parsed = _parse_json_field(sections_text)
	sections = [s for s in parsed if isinstance(s, str)] if isinstance(parsed, list) else []
	return {"collapsed_sections": sections}
