import frappe
from frappe import _
from frappe.model import get_permitted_fields
from frappe.utils import cint

EXCLUDED_FIELDTYPES = {
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Table",
	"Table MultiSelect",
	"Fold",
	"Heading",
	"Image",
}

STANDARD_FIELDS = (
	{"fieldname": "name", "fieldtype": "Data", "label": "ID", "options": ""},
	{"fieldname": "owner", "fieldtype": "Link", "label": "Created By", "options": "User"},
	{"fieldname": "creation", "fieldtype": "Datetime", "label": "Created On", "options": ""},
	{
		"fieldname": "modified_by",
		"fieldtype": "Link",
		"label": "Last Updated By",
		"options": "User",
	},
	{"fieldname": "modified", "fieldtype": "Datetime", "label": "Last Updated On", "options": ""},
)

DOCSTATUS_FIELD = {
	"fieldname": "docstatus",
	"fieldtype": "Int",
	"label": "Document Status",
	"options": "",
}


def _as_list(value, argument_name):
	if isinstance(value, str):
		try:
			value = frappe.parse_json(value)
		except (TypeError, ValueError):
			frappe.throw(_("{0} must be a valid JSON list.").format(argument_name))
	if value is None:
		return []
	if not isinstance(value, (list, tuple)):
		frappe.throw(_("{0} must be a list.").format(argument_name))
	return list(value)


def _view_fieldnames(view_fields):
	return {
		fieldname.strip()
		for fieldname in _as_list(view_fields, _("View fields"))
		if isinstance(fieldname, str) and fieldname.strip()
	}


def _field_payload(df):
	return {
		"fieldname": df.fieldname,
		"fieldtype": df.fieldtype or "Data",
		"label": df.label or df.fieldname,
		"options": df.options or "",
		"precision": df.precision,
		"link_filters": df.link_filters or "",
		"hidden": cint(df.hidden),
		"in_list_view": cint(df.in_list_view),
		"in_standard_filter": cint(df.in_standard_filter),
	}


def _has_field_access(df, permitted, masked, readable_permlevels):
	return bool(
		df.fieldname
		and df.fieldname in permitted
		and df.fieldname not in masked
		and (cint(df.permlevel) == 0 or cint(df.permlevel) in readable_permlevels)
	)


def _list_field_settings(doctype_name, view_fields=None):
	permission_type = "select" if frappe.only_has_select_perm(doctype_name) else "read"
	frappe.has_permission(doctype_name, ptype=permission_type, throw=True)
	meta = frappe.get_meta(doctype_name)
	permitted = set(
		get_permitted_fields(
			doctype_name,
			permission_type=permission_type,
			ignore_virtual=True,
		)
	)
	readable_permlevels = set(meta.get_permlevel_access(parenttype=doctype_name))
	masked = {df.fieldname for df in meta.get_masked_fields()}
	visible_hidden_fields = _view_fieldnames(view_fields)

	fields = []
	standard_by_name = {field["fieldname"]: field for field in STANDARD_FIELDS}
	if "name" in permitted:
		fields.append(dict(standard_by_name["name"]))

	for df in meta.fields:
		if (
			not _has_field_access(df, permitted, masked, readable_permlevels)
			or df.fieldtype in EXCLUDED_FIELDTYPES
			or (cint(df.hidden) and df.fieldname not in visible_hidden_fields)
		):
			continue
		fields.append(_field_payload(df))

	for field in STANDARD_FIELDS[1:]:
		if field["fieldname"] in permitted:
			fields.append(dict(field))
	if cint(meta.is_submittable) and "docstatus" in permitted:
		fields.append(dict(DOCSTATUS_FIELD))

	currency_fields = {}
	for field in fields:
		if field["fieldtype"] != "Currency":
			continue
		reference_name = str(field["options"] or "").strip()
		reference_df = meta.get_field(reference_name) if reference_name else None
		if not reference_df:
			reference_name = "currency"
			reference_df = meta.get_field(reference_name)
		if reference_df and _has_field_access(
			reference_df,
			permitted,
			masked,
			readable_permlevels,
		):
			currency_fields[field["fieldname"]] = reference_name

	return fields, currency_fields


def get_allowed_list_fields(doctype_name, view_fields=None):
	return _list_field_settings(doctype_name, view_fields)[0]


def _saved_listview_name(doctype_name):
	return frappe.db.get_value(
		"YRP User Listview",
		{"user": frappe.session.user, "doctype_name": doctype_name},
		"name",
	)


def _saved_columns(doctype_name, allowed_names):
	name = _saved_listview_name(doctype_name)
	if not name:
		return None
	return [
		{"fieldname": row.fieldname, "enabled": cint(row.enabled)}
		for row in frappe.get_all(
			"YRP User Listview Field",
			filters={"parent": name},
			fields=["fieldname", "enabled"],
			order_by="idx asc",
		)
		if row.fieldname in allowed_names
	]


@frappe.whitelist()
def get_user_listview(doctype_name, view_fields=None):
	fields, currency_fields = _list_field_settings(doctype_name, view_fields)
	allowed_names = {field["fieldname"] for field in fields}
	return {
		"fields": fields,
		"columns": _saved_columns(doctype_name, allowed_names),
		"currency_fields": currency_fields,
	}


def _validated_columns(columns, allowed_fields):
	allowed_by_name = {field["fieldname"]: field for field in allowed_fields}
	validated = []
	seen = set()
	submitted_columns = _as_list(columns, _("Columns"))
	if not submitted_columns:
		frappe.throw(_("At least one column must be submitted."))
	for column in submitted_columns:
		if not isinstance(column, dict):
			frappe.throw(_("Each column must be an object."))
		fieldname = str(column.get("fieldname") or "").strip()
		if not fieldname or fieldname not in allowed_by_name:
			frappe.throw(_("Field {0} is not available for this list.").format(frappe.bold(fieldname or "?")))
		if fieldname in seen:
			frappe.throw(_("Field {0} was submitted more than once.").format(frappe.bold(fieldname)))
		seen.add(fieldname)
		validated.append((allowed_by_name[fieldname], cint(column.get("enabled"))))
	return validated


@frappe.whitelist()
def save_user_listview(doctype_name, columns, view_fields=None):
	validated = _validated_columns(
		columns,
		get_allowed_list_fields(doctype_name, view_fields),
	)
	name = _saved_listview_name(doctype_name)
	if name:
		doc = frappe.get_doc("YRP User Listview", name)
	else:
		doc = frappe.new_doc("YRP User Listview")
		doc.user = frappe.session.user
		doc.doctype_name = doctype_name

	doc.set("fields", [])
	for field, enabled in validated:
		doc.append(
			"fields",
			{
				"fieldname": field["fieldname"],
				"fieldtype": field["fieldtype"],
				"label": field["label"],
				"enabled": enabled,
			},
		)
	doc.save(ignore_permissions=True)
	return "ok"


@frappe.whitelist()
def reset_user_listview(doctype_name):
	name = _saved_listview_name(doctype_name)
	if name:
		frappe.delete_doc("YRP User Listview", name, ignore_permissions=True, force=True)
	return "ok"
