"""Bulk field edit helpers for the /web list view."""

import json

import frappe
from frappe import _
from frappe.model import data_fieldtypes
from frappe.utils import cint, flt, strip_html_tags


DISALLOWED_FIELDTYPES = {"Dynamic Link", "Read Only"}


def _as_list(value):
	if isinstance(value, str):
		return frappe.parse_json(value)
	return value or []


def _clean_message(value):
	return strip_html_tags(str(value or "")).strip()


def _pop_messages():
	messages = []
	for msg in getattr(frappe.local, "message_log", []) or []:
		if isinstance(msg, dict):
			messages.append(msg.get("message") or msg.get("title") or "")
		else:
			messages.append(str(msg))
	frappe.local.message_log = []
	return "; ".join(filter(None, (_clean_message(m) for m in messages)))


def _error_message(exc):
	return _pop_messages() or _clean_message(exc) or _("Failed")


def _is_bulk_editable(df, allowed_permlevels):
	return (
		df
		and df.fieldname
		and df.fieldtype in data_fieldtypes
		and df.fieldtype not in DISALLOWED_FIELDTYPES
		and not cint(df.hidden)
		and not cint(df.read_only)
		and not cint(df.get("is_virtual"))
		and cint(df.permlevel or 0) in allowed_permlevels
	)


def _field_payload(df, *, is_child_field=False, child_doctype=None, parent_table_field=None, parent_table_label=None):
	label = df.label or df.fieldname
	if is_child_field and parent_table_label:
		label = _("{0} ({1})").format(label, parent_table_label)
	return {
		"key": (
			f"{child_doctype}:{parent_table_field}:{df.fieldname}"
			if is_child_field
			else df.fieldname
		),
		"label": label,
		"fieldname": df.fieldname,
		"fieldtype": df.fieldtype,
		"options": df.options or "",
		"reqd": cint(df.reqd),
		"permlevel": cint(df.permlevel or 0),
		"allow_on_submit": cint(df.allow_on_submit),
		"is_child_field": bool(is_child_field),
		"child_doctype": child_doctype,
		"parent_table_field": parent_table_field,
		"parent_table_label": parent_table_label,
	}


def _bulk_edit_fields(doctype):
	meta = frappe.get_meta(doctype)
	parent_write_levels = set(meta.get_permlevel_access("write"))
	fields = []

	for df in meta.fields:
		if _is_bulk_editable(df, parent_write_levels):
			fields.append(_field_payload(df))

		if df.fieldtype != "Table" or not df.options:
			continue
		if cint(df.hidden) or cint(df.read_only) or cint(df.permlevel or 0) not in parent_write_levels:
			continue

		child_meta = frappe.get_meta(df.options)
		child_write_levels = set(child_meta.get_permlevel_access("write", parenttype=doctype))
		for child_df in child_meta.fields:
			if _is_bulk_editable(child_df, child_write_levels):
				fields.append(
					_field_payload(
						child_df,
						is_child_field=True,
						child_doctype=child_meta.name,
						parent_table_field=df.fieldname,
						parent_table_label=df.label or df.fieldname,
					)
				)

	return fields


def _resolve_field(doctype, fieldname, child_doctype=None, parent_table_field=None):
	for field in _bulk_edit_fields(doctype):
		if field["fieldname"] != fieldname:
			continue
		if child_doctype or parent_table_field:
			if (
				field.get("child_doctype") == child_doctype
				and field.get("parent_table_field") == parent_table_field
			):
				return field
		elif not field.get("is_child_field"):
			return field
	frappe.throw(_("Field {0} cannot be bulk edited.").format(fieldname))


def _coerce_value(value, fieldtype):
	if value == "":
		value = None
	if fieldtype == "Check":
		return cint(value)
	if value is None:
		return None
	if fieldtype in {"Int", "Long Int"}:
		return cint(value)
	if fieldtype in {"Float", "Currency", "Percent", "Duration", "Rating"}:
		return flt(value)
	if fieldtype == "JSON" and isinstance(value, (dict, list)):
		return json.dumps(value)
	return value


def _validate_selected_link(field, value):
	if value in (None, "") or field["fieldtype"] != "Link":
		return
	target = field.get("options")
	if target and not frappe.db.exists(target, value):
		frappe.throw(_("Could not find {0}: {1}").format(target, value), frappe.LinkValidationError)


def _validate_selected_value(field, value):
	if field.get("reqd") and value in (None, ""):
		frappe.throw(_("{0} is required.").format(field.get("label") or field["fieldname"]))
	_validate_selected_link(field, value)


def _clear_zero_link_values(doc):
	"""Clean legacy optional Link placeholders before saving selected docs."""
	def clear(target):
		for df in target.meta.fields:
			if df.fieldtype == "Link" and not cint(df.reqd) and target.get(df.fieldname) in ("", 0, "0"):
				target.set(df.fieldname, None)

	clear(doc)
	for child in doc.get_all_children():
		clear(child)


def _prepare_for_bulk_save(doc):
	# YRP stock doctypes keep the grouped Vue editor payload in item_details.
	# Bulk edit changes a single field, so do not let a stale hidden payload
	# rebuild child rows and change their names during save.
	if doc.meta.has_field("item_details"):
		doc.set("item_details", None)
	_clear_zero_link_values(doc)
	doc.flags.ignore_links = True


@frappe.whitelist()
def get_bulk_edit_fields(doctype):
	"""Return fields the current user can write by permlevel."""
	if not doctype:
		return []
	# Don't leak field metadata of arbitrary doctypes to any logged-in user —
	# the caller must at least be able to read the doctype it asks about.
	frappe.has_permission(doctype, "read", throw=True)
	return sorted(_bulk_edit_fields(doctype), key=lambda f: _clean_message(f["label"]).lower())


@frappe.whitelist()
def bulk_update_field(doctype, docnames, fieldname, value=None, child_doctype=None, parent_table_field=None):
	"""Set one parent or child-table field across selected documents.

	The field is resolved through get_bulk_edit_fields() so the client cannot
	submit a hidden/read-only/high-permlevel field by hand. A child-table field
	is applied via doc.save() (full controller validation); a parent field is
	applied via doc.db_set() — a targeted write that SKIPS validate/before_save
	(intentional for a single-column bulk edit), still permission- and
	docstatus-gated below.
	"""
	docnames = _as_list(docnames)
	if not doctype:
		frappe.throw(_("DocType is required."))
	if not docnames:
		frappe.throw(_("Select at least one document."))
	if len(docnames) > 500:
		frappe.throw(_("Bulk operations only support up to 500 documents."))

	field = _resolve_field(doctype, fieldname, child_doctype, parent_table_field)
	value = _coerce_value(value, field["fieldtype"])
	_validate_selected_value(field, value)
	updated = []
	failures = []

	for name in docnames:
		try:
			doc = frappe.get_doc(doctype, name)
			doc.check_permission("write")
			if doc.docstatus == 2:
				frappe.throw(_("Cancelled documents cannot be updated."))
			if doc.docstatus == 1 and not field.get("allow_on_submit"):
				frappe.throw(_("{0} cannot be updated after submit.").format(field.get("label") or fieldname))

			if field.get("is_child_field"):
				children = doc.get(parent_table_field) or []
				for child in children:
					child.set(fieldname, value)
				_prepare_for_bulk_save(doc)
				doc.save()
			else:
				doc.db_set(fieldname, value, update_modified=True)
			frappe.db.commit()
			updated.append(name)
		except Exception as exc:
			frappe.db.rollback()
			failures.append({"name": name, "message": _error_message(exc)})

	return {"updated": updated, "failures": failures}
