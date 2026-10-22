import frappe
from frappe import _
from frappe.model import optional_fields

DROPPED_FIELDS = ("amended_from", "__islocal", "__unsaved", *optional_fields)


@frappe.whitelist()
def get_duplicate_values(doctype: str, name: str) -> dict:
	return build_duplicate_values(doctype, name)


def build_duplicate_values(doctype: str, name: str) -> dict:
	"""Return an unsaved draft copy of a document as plain field values."""
	meta = frappe.get_meta(doctype)
	if meta.allow_copy or meta.issingle or meta.istable:
		frappe.throw(_("{0} documents cannot be duplicated.").format(_(doctype)))
	source = frappe.get_doc(doctype, name)
	source.check_permission("read")
	if not frappe.has_permission(doctype, "create"):
		frappe.throw(_("Not permitted to create {0}.").format(_(doctype)), frappe.PermissionError)
	return as_draft_values(frappe.copy_doc(source, ignore_no_copy=False))


def as_draft_values(doc) -> dict:
	values = doc.as_dict(no_default_fields=True, no_child_table_fields=True)
	for fieldname in DROPPED_FIELDS:
		values.pop(fieldname, None)
	for table_field in doc.meta.get_table_fields():
		values[table_field.fieldname] = [
			{"doctype": row.doctype, **{key: value for key, value in row_values.items() if key not in DROPPED_FIELDS}}
			for row, row_values in zip(doc.get(table_field.fieldname), values.get(table_field.fieldname) or [], strict=True)
		]
	return {"doctype": doc.doctype, "docstatus": 0, **values}
