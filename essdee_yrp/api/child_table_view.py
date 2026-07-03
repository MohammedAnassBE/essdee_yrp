"""Per-user, server-side store for SPA child-table column view settings.

The SPA's child-table grids (DocDetail.vue) let each user choose which columns
are visible and drag per-column widths. Those choices used to live in browser
localStorage; this module persists them server-side in the
"Essdee Child Table View Setting" DocType so a user sets them once and they follow
the user across server restarts AND across browsers/devices.

Both endpoints are scoped to ``frappe.session.user`` — a user can never read or
write another user's row. The internal read/write uses ``ignore_permissions``
because normal SPA users have no role on the setting DocType (it is an internal
preference store, not user-facing data); per-user isolation is enforced here in
code, not via the doctype permission rules.
"""

import json

import frappe
from frappe import _

SETTING_DOCTYPE = "Essdee Child Table View Setting"


def _required(value, label):
	"""Return a stripped non-empty string or throw a clear validation error."""
	value = (value or "").strip() if isinstance(value, str) else value
	if not value:
		frappe.throw(_("{0} is required").format(label))
	return value


def _parse_json_field(raw):
	"""Decode a stored Long Text JSON field; tolerate empty / malformed values."""
	if not raw:
		return None
	try:
		return json.loads(raw)
	except (ValueError, TypeError):
		return None


def _coerce_to_json_text(value, *, kind):
	"""Normalise an incoming visible_columns / column_widths value to JSON text.

	Accepts either a JSON string (from the JSON request body) or an already
	decoded list/dict. ``kind`` is "list" or "obj" — it selects the empty
	default so the stored value is always valid JSON of the expected shape.
	"""
	if isinstance(value, str):
		try:
			value = json.loads(value) if value.strip() else None
		except (ValueError, TypeError):
			value = None
	if value is None:
		value = [] if kind == "list" else {}
	return json.dumps(value)


def _find_existing(user, parent_doctype, child_table):
	"""Name of this user's row for (parent_doctype, child_table), or None."""
	return frappe.db.get_value(
		SETTING_DOCTYPE,
		{
			"user": user,
			"parent_doctype": parent_doctype,
			"child_table": child_table,
		},
		"name",
	)


def _update_existing(name, visible_text, widths_text):
	"""Load the row by name and persist the new visible/width JSON."""
	doc = frappe.get_doc(SETTING_DOCTYPE, name)
	doc.visible_columns = visible_text
	doc.column_widths = widths_text
	doc.save(ignore_permissions=True)


@frappe.whitelist()
def get_view(parent_doctype, child_table):
	"""Return the current user's saved column view for one child table.

	@returns {"visible_columns": <list|null>, "column_widths": <obj>}
	  - visible_columns: list of fieldnames, or null when the user has never
	    saved a selection (SPA then falls back to its default-visible set).
	  - column_widths: {fieldname: px}, or {} when none saved.
	"""
	user = frappe.session.user
	parent_doctype = _required(parent_doctype, _("Parent Doctype"))
	child_table = _required(child_table, _("Child Table"))

	name = _find_existing(user, parent_doctype, child_table)
	if not name:
		return {"visible_columns": None, "column_widths": {}}

	row = frappe.db.get_value(
		SETTING_DOCTYPE,
		name,
		["visible_columns", "column_widths"],
		as_dict=True,
	)

	visible = _parse_json_field(row.visible_columns) if row else None
	widths = _parse_json_field(row.column_widths) if row else None
	return {
		"visible_columns": visible if isinstance(visible, list) else None,
		"column_widths": widths if isinstance(widths, dict) else {},
	}


@frappe.whitelist()
def save_view(parent_doctype, child_table, visible_columns=None, column_widths=None):
	"""Upsert the current user's column view for one child table.

	visible_columns / column_widths may arrive as JSON strings (from the request
	body) or as already-decoded list/dict; both are normalised to JSON text and
	stored. The row is always keyed to ``frappe.session.user`` so a user can
	only ever write their own settings.

	@returns the saved view in the same shape as get_view().
	"""
	user = frappe.session.user
	parent_doctype = _required(parent_doctype, _("Parent Doctype"))
	child_table = _required(child_table, _("Child Table"))

	visible_text = _coerce_to_json_text(visible_columns, kind="list")
	widths_text = _coerce_to_json_text(column_widths, kind="obj")

	name = _find_existing(user, parent_doctype, child_table)
	if name:
		# Fast path: row already exists for this (user, parent_doctype,
		# child_table) — update it in place.
		_update_existing(name, visible_text, widths_text)
	else:
		# No row found. The insert may still race a concurrent save for the SAME
		# triple (e.g. an immediate toggle-save racing the 400ms debounced
		# resize-save): both can miss the find above. The row is deterministically
		# named from the triple (see the controller's autoname), so a concurrent
		# insert collides on the primary key instead of silently duplicating. We
		# wrap the insert in a savepoint so that, on collision, only the failed
		# insert is rolled back (not the whole request transaction); then we
		# re-fetch the now-existing row and update it so this save is not dropped.
		savepoint = "essdee_ctv_insert"
		frappe.db.savepoint(savepoint)
		try:
			doc = frappe.get_doc(
				{
					"doctype": SETTING_DOCTYPE,
					"user": user,
					"parent_doctype": parent_doctype,
					"child_table": child_table,
					"visible_columns": visible_text,
					"column_widths": widths_text,
				}
			)
			doc.insert(ignore_permissions=True)
		except frappe.exceptions.DuplicateEntryError:
			# Lost the race — the row now exists. Undo the failed insert, then
			# re-fetch by the 3 filters and update it instead.
			frappe.db.rollback(save_point=savepoint)
			existing = _find_existing(user, parent_doctype, child_table)
			if existing:
				_update_existing(existing, visible_text, widths_text)

	visible = _parse_json_field(visible_text)
	widths = _parse_json_field(widths_text)
	return {
		"visible_columns": visible if isinstance(visible, list) else None,
		"column_widths": widths if isinstance(widths, dict) else {},
	}
