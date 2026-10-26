import frappe
from frappe.model import no_value_fields, table_fields
from frappe.utils import cint, cstr, flt

APPENDABLE_TABLE = "ipd_processes"
EMBELLISHMENT_FIELD = "emblishment_details_json"
APPROVED_EDIT_FIELDS = (APPENDABLE_TABLE, EMBELLISHMENT_FIELD)
NUMERIC_FIELDTYPES = ("Float", "Currency", "Percent")
INTEGER_FIELDTYPES = ("Int", "Check")


def get_approved_edit_changes(doc, before) -> tuple[list[str], bool]:
	"""Compare a save of an Approved IPD with its stored copy.

	Returns the labels of locked fields that changed, and whether an allowed edit
	(new IPD Processes rows or Embellishment panel changes) is present.
	"""
	locked = []
	allowed = False
	for df in doc.meta.fields:
		if df.fieldname == APPENDABLE_TABLE:
			appended, valid = get_appended_rows(doc, before)
			allowed = allowed or appended
			if not valid:
				locked.append(df.label)
		elif df.fieldname == EMBELLISHMENT_FIELD:
			panels_changed, valid = get_embellishment_change(doc, before)
			allowed = allowed or panels_changed
			if not valid:
				locked.append(df.label)
		elif df.fieldtype in table_fields:
			if get_rows(doc, df) != get_rows(before, df):
				locked.append(df.label)
		elif df.fieldtype not in no_value_fields:
			if normalize(df, doc.get(df.fieldname)) != normalize(df, before.get(df.fieldname)):
				locked.append(df.label or df.fieldname)
	return locked, allowed


def get_appended_rows(doc, before) -> tuple[bool, bool]:
	"""Return (rows were appended, stored rows are untouched)."""
	df = doc.meta.get_field(APPENDABLE_TABLE)
	stored = get_rows(before, df)
	incoming = get_rows(doc, df)
	stored_names = {row.name for row in before.get(APPENDABLE_TABLE) or []}
	new_rows = (doc.get(APPENDABLE_TABLE) or [])[len(stored) :]
	untouched = incoming[: len(stored)] == stored and not any(row.name in stored_names for row in new_rows)
	return len(incoming) > len(stored), untouched


def get_embellishment_change(doc, before) -> tuple[bool, bool]:
	"""Return (panels changed, the embellishment processes are unchanged)."""
	incoming = frappe.parse_json(doc.get(EMBELLISHMENT_FIELD)) or {}
	stored = frappe.parse_json(before.get(EMBELLISHMENT_FIELD)) or {}
	if not isinstance(incoming, dict) or set(incoming) != set(stored):
		return False, False
	if not all(isinstance(panels, list) for panels in incoming.values()):
		return False, False
	return any(incoming[process] != stored[process] for process in stored), True


def get_rows(doc, df) -> list[tuple]:
	child_fields = [
		child for child in frappe.get_meta(df.options).fields if child.fieldtype not in no_value_fields
	]
	return [
		(row.name, *(normalize(child, row.get(child.fieldname)) for child in child_fields))
		for row in doc.get(df.fieldname) or []
	]


def normalize(df, value):
	if df.fieldtype in NUMERIC_FIELDTYPES:
		return flt(value)
	if df.fieldtype in INTEGER_FIELDTYPES:
		return cint(value)
	if value in (None, ""):
		return None
	if df.fieldtype == "JSON":
		return frappe.parse_json(value)
	return cstr(value)
