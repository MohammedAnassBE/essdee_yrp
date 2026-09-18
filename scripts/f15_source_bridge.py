#!/usr/bin/env python3
"""Read-only JSON-lines bridge for a configured F15 Production API source.

Run this file with the Frappe-15 virtualenv.  It never writes or commits and is
given its bench, site, and supported app by the server-owned target profile.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import runpy
import os
import re
import sys
import warnings
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]+$")
SAFE_FIELDNAME = re.compile(r"^[a-z][a-z0-9_]*$")
SYSTEM_FIELDS = (
	"name",
	"owner",
	"creation",
	"modified",
	"modified_by",
	"docstatus",
	"idx",
	"parent",
	"parentfield",
	"parenttype",
	"_user_tags",
	"_comments",
	"_assign",
	"_liked_by",
	"_seen",
)
NO_VALUE_FIELD_TYPES = {
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Heading",
	"Fold",
}
SUPPORTING_EXTERNAL_DOCTYPES = {
	"Address",
	"Contact",
	"Email Account",
	"Letter Head",
	"Print Format",
	"Role",
	"User",
	"Workflow State",
}

# Frappe records approved by the owner for active (not archive-only) migration.
# Energy Point Settings and S3 Backup Settings existed in F15, but Frappe 16 no
# longer provides either DocType; they therefore cannot be live routes.  Spine
# data remains excluded independently of these selections.
APPROVED_FRAPPE_DATA_ORDER = (
	"Role",
	"Address Template",
	"Letter Head",
	"Email Domain",
	"Email Account",
	"Module Profile",
	"User",
	"Custom DocPerm",
	"Dashboard Settings",
	"DefaultValue",
	"Email Unsubscribe",
	"List View Settings",
	"Note",
	"Notification Settings",
	"Print Settings",
	"System Settings",
	"Website Settings",
	"Workspace",
)
APPROVED_FRAPPE_CHILD_DOCTYPES = frozenset(
	{
		"Block Module",
		"Has Role",
		"IMAP Folder",
		"Note Seen By",
		"Notification Subscribed Document",
		"DefaultValue",
		"User Email",
		"User Social Login",
		"Top Bar Item",
		"Website Route Redirect",
		"Workspace Chart",
		"Workspace Shortcut",
		"Workspace Link",
		"Workspace Quick List",
		"Workspace Number Card",
		"Workspace Custom Block",
	}
)
APPROVED_FRAPPE_ARCHIVE_ONLY_DOCTYPES = (
	# Frappe 16 moved these features to optional apps and has no target DocType.
	# Their complete F15 Single rows (and matching __Auth rows) stay in the
	# encrypted, byte-verified framework archive instead of being dropped.
	"Energy Point Settings",
	"S3 Backup Settings",
)
APPROVED_FRAPPE_ARCHIVE_PREFIX = "Approved Frappe Exact::"
UNSAFE_SYSTEM_DEFAULT_KEYS = frozenset(
	{
		"enable_scheduler",
		"installed_apps",
		"is_first_startup",
		"setup_complete",
	}
)
REMOVED_FRAPPE_FIELDS = {
	"List View Settings": frozenset({"total_fields"}),
	"Notification Settings": frozenset(
		{"enable_email_energy_point", "energy_points_system_notifications"}
	),
	"System Settings": frozenset({"allow_older_web_view_links", "setup_complete"}),
}
RETIRED_SOURCE_TABLES = (
	# Historical Production API tables whose DocTypes were removed/renamed.
	# Keep raw snapshots, not live operational rows: successor records can differ.
	"WO Debit",
	"Employee Department",
	"Item Production Detail Cloth Accessories",
	# Two orphan dashboard access rows also remain in this source database.
	# Archive only; never recreate or activate their retired permission rules.
	"Custom User Dashboard",
	"Custom User Dashboard User",
)
SOURCE_SCHEMA_OVERLAYS = {
	# These physical columns/child rows remain on the source site but were
	# removed from its latest runtime metadata. Owner-approved empty/default
	# columns are included too: the one-pass migration must export the complete
	# historical schema, not only columns that happen to be populated today.
	"Cutting Laysheet Planner": [
		{
			"fieldname": "lot",
			"fieldtype": "Link",
			"label": "Lot",
			"options": "Lot",
		},
		{
			"fieldname": "description",
			"fieldtype": "Small Text",
			"label": "Description",
		},
		{
			"fieldname": "item",
			"fieldtype": "Link",
			"label": "Item",
			"options": "Item",
		},
	],
	"FG Stock Entry": [
		{"fieldname": "lot", "label": "Lot", "fieldtype": "Link", "options": "Lot"}
	],
	"Essdee Quality Inspection": [
		{
			"fieldname": "unit_name",
			"fieldtype": "Link",
			"in_list_view": 1,
			"in_standard_filter": 1,
			"label": "Unit Name",
			"options": "Supplier",
			"read_only": 1,
		}
	],
	"Essdee Raw Print Format": [
		{"fieldname": "raw_code", "fieldtype": "Code", "label": "Raw Code"}
	],
	"Cut Panel Movement": [
		{
			"fieldname": "process_name",
			"fieldtype": "Link",
			"label": "Process Name",
			"options": "Process",
			"reqd": 1,
		}
	],
	"Cutting Marker": [
		{
			"depends_on": "eval: !doc.__islocal && doc.item",
			"fieldname": "cutting_marker_parts",
			"fieldtype": "Table",
			"label": "Cutting Marker Parts",
			"options": "Cutting Marker Part",
		}
	],
	"Lot": [
		{
			"fieldname": "version",
			"fieldtype": "Select",
			"label": "Version",
			"options": "\nV1\nV2",
			"read_only": 1,
		},
		{
			"default": "0",
			"fieldname": "capacity_planning",
			"fieldtype": "Check",
			"label": "Capacity Planning",
		},
		{
			"fieldname": "primary_item_attribute",
			"fieldtype": "Link",
			"label": "Primary Item Attribute",
			"options": "Item Attribute",
		},
	],
	"Lotwise Item Profit Qty Rate": [
		{
			"default": "1",
			"fieldname": "ratio",
			"fieldtype": "Int",
			"label": "Ratio",
		},
		{
			"columns": 1,
			"fieldname": "weight",
			"fieldtype": "Float",
			"in_list_view": 1,
			"label": "Weight",
			"precision": "9",
		},
	],
	"Goods Received Note": [
		{
			"fieldname": "billing_address",
			"fieldtype": "Link",
			"label": "Billing Address",
			"options": "Address",
		},
		{
			"fieldname": "billing_address_display",
			"fieldtype": "Small Text",
			"label": "Billing Address Details",
			"read_only": 1,
		},
	],
	"Goods Received Note Item": [
		{
			"allow_on_submit": 1,
			"columns": 1,
			"fieldname": "received_quantity",
			"fieldtype": "Float",
			"in_list_view": 1,
			"label": "Received Quantity",
			"precision": "9",
		},
		{
			"fieldname": "rework_details",
			"fieldtype": "Small Text",
			"label": "Rework Details",
		},
	],
	"Item BOM": [
		{
			"fieldname": "attribute_mapping_based_on",
			"fieldtype": "Link",
			"in_list_view": 1,
			"label": "Attribute mapping based on ",
			"options": "Item Attribute",
		}
	],
	"Item BOM Attribute Mapping Value": [
		{
			"fieldname": "bom_item_attribute",
			"fieldtype": "Link",
			"in_list_view": 1,
			"label": "BOM Item Attribute",
			"options": "Item Attribute Value",
		},
		{
			"fieldname": "product_attribute",
			"fieldtype": "Link",
			"in_list_view": 1,
			"label": "Product Attribute",
			"options": "Item Attribute Value",
		},
	],
	"Item Price": [
		{
			"fieldname": "price",
			"fieldtype": "Float",
			"in_list_view": 1,
			"label": "Price",
			"precision": "9",
		}
	],
	"Item BOM Attribute Mapping": [
		{
			"fieldname": "lot_template",
			"fieldtype": "Link",
			"label": "Lot Template",
			"options": "Lot Template",
		}
	],
	"Item Production Detail": [
		{
			"fieldname": "additional_cloth",
			"fieldtype": "Float",
			"label": "Additional Cloth %",
		},
		{
			"fieldname": "stiching_attribute_quantity",
			"fieldtype": "Int",
			"label": "Stiching Attribute Quantity",
		},
	],
	"Process Cost": [
		{
			"depends_on": "eval: doc.depends_on_attribute",
			"fieldname": "dependent_attribute",
			"fieldtype": "Link",
			"label": "Dependent Attribute",
			"options": "Item Attribute",
		},
		{
			"depends_on": "eval: doc.depends_on_attribute",
			"fieldname": "dependent_attribute_values",
			"fieldtype": "Select",
			"label": "Dependent Attribute Values",
		},
	],
	"Production Items": [
		{
			"fieldname": "process_name",
			"fieldtype": "Link",
			"in_list_view": 1,
			"label": "Process Name",
			"options": "Process",
		}
	],
	"Production Order": [
		{
			"fieldname": "production_detail",
			"fieldtype": "Link",
			"label": "Production Detail",
			"options": "Item Production Detail",
		}
	],
	"Purchase Invoice": [
		{
			"fieldname": "debit_type",
			"fieldtype": "Select",
			"label": "Debit Type",
			"options": "\nPermanent\nTemporary",
		},
		{"fieldname": "debit_no", "fieldtype": "Data", "label": "Debit No"},
		{
			"fieldname": "debit_value",
			"fieldtype": "Currency",
			"label": "Debit Value",
			"precision": "9",
		},
	],
	"Purchase Order": [
		{
			"fieldname": "billing_address",
			"fieldtype": "Link",
			"label": "Billing Address",
			"options": "Address",
		},
		{
			"fieldname": "billing_address_display",
			"fieldtype": "Small Text",
			"label": "Billing Address Details",
			"read_only": 1,
		},
	],
	"Sewing Plan": [
		{
			"fieldname": "strength_report_date",
			"fieldtype": "Date",
			"label": "Strength Report Date",
		},
		{
			"fieldname": "strength_report_from_time",
			"fieldtype": "Time",
			"label": "Strength Report From Time",
		},
		{
			"fieldname": "strength_report_to_time",
			"fieldtype": "Time",
			"label": "Strength Report To Time",
		},
	],
	"Supplier": [
		{
			"fieldname": "deparments",
			"fieldtype": "Table MultiSelect",
			"label": "Departments",
			"options": "Supplier Department",
		}
	],
}


def _load_schemas(source_app_root, supporting_schema_roots):
	schemas = {}
	paths = list(source_app_root.rglob("*.json"))
	for root in supporting_schema_roots:
		paths.extend(root.rglob("*.json"))
	for path in sorted(paths):
		try:
			value = json.loads(path.read_text())
		except Exception:
			continue
		if isinstance(value, dict) and value.get("doctype") == "DocType" and value.get("name"):
			schemas[value["name"]] = value
	return schemas


def _runtime_schema(frappe, doctype, declared):
	meta = frappe.get_meta(doctype, cached=False)
	schema = {
		"doctype": "DocType",
		"name": doctype,
		"module": getattr(meta, "module", None) or declared.get("module"),
		"istable": int(bool(getattr(meta, "istable", declared.get("istable")))),
		"issingle": int(bool(getattr(meta, "issingle", declared.get("issingle")))),
		"autoname": getattr(meta, "autoname", None) or declared.get("autoname"),
		"fields": [field.as_dict() for field in meta.fields],
	}
	existing = {field.get("fieldname") for field in schema["fields"]}
	for field in SOURCE_SCHEMA_OVERLAYS.get(doctype, []):
		if field.get("fieldname") not in existing:
			schema["fields"].append(dict(field))
	return schema


def _load_runtime_schemas(frappe, declared_schemas):
	"""Overlay the approved source catalog with the metadata actually in F15.

	Production API historically changed some DocTypes through migrations and
	Property Setters, so the checked-out JSON is not always the complete live
	contract.  Keep the catalog restricted to version-controlled source
	DocTypes, but read their effective fields from ``frappe.get_meta``.
	"""

	runtime = {}
	for doctype, declared in declared_schemas.items():
		runtime[doctype] = _runtime_schema(frappe, doctype, declared)
	return runtime


def _load_export_schemas(frappe, declared_schemas, parent_doctype):
	"""Load effective metadata only for one export tree."""

	if parent_doctype not in declared_schemas:
		return declared_schemas
	runtime = dict(declared_schemas)
	pending = [parent_doctype]
	loaded = set()
	while pending:
		doctype = pending.pop()
		if doctype in loaded:
			continue
		loaded.add(doctype)
		schema = _runtime_schema(frappe, doctype, declared_schemas[doctype])
		runtime[doctype] = schema
		for field in _table_fields(schema):
			child_doctype = field.get("options")
			if child_doctype in declared_schemas and child_doctype not in loaded:
				pending.append(child_doctype)
	return runtime


def emit_schemas(schemas):
	for doctype in sorted(schemas):
		_write({"kind": "schema", "schema": schemas[doctype]})


def emit_orphan_children(frappe, schemas, batch_size=500):
	"""Preserve physical child rows whose historical parent no longer exists.

	Every populated parent context must still have a declared migration route.
	Unknown contexts fail closed instead of silently omitting their records.
	"""
	for doctype, schema in sorted(schemas.items()):
		if not schema.get("istable"):
			continue
		table = _quote_identifier("tab" + doctype)
		contexts = frappe.db.sql(
			f"SELECT DISTINCT parenttype, parentfield FROM {table}"
		)
		for parenttype, parentfield in contexts:
			parent_schema = schemas.get(parenttype)
			field = next(
				(field for field in _table_fields(parent_schema or {})
				 if field["fieldname"] == parentfield and field["options"] == doctype),
				None,
			)
			if not parent_schema or not field:
				raise RuntimeError(
					f"Unmapped physical child context {doctype}: {parenttype}.{parentfield}"
				)
			if parent_schema.get("issingle"):
				join = ""
				missing = "child.parent<>%s"
				values = [parenttype, parentfield, parenttype]
			else:
				join = (
					f"LEFT JOIN {_quote_identifier('tab' + parenttype)} parent "
					"ON parent.name=child.parent"
				)
				missing = "parent.name IS NULL"
				values = [parenttype, parentfield]
			last_name = ""
			fields = ", ".join(
				"child." + _quote_identifier(fieldname)
				for fieldname in _query_fields(frappe, doctype, schema)
			)
			while True:
				rows = frappe.db.sql(
					f"SELECT {fields} FROM {table} child {join} "
					"WHERE child.parenttype=%s AND child.parentfield=%s "
					f"AND {missing} AND child.name>%s ORDER BY child.name LIMIT %s",
					[*values, last_name, batch_size], as_dict=True,
				)
				if not rows:
					break
				for row in rows:
					row["doctype"] = doctype
					_add_passwords(frappe, doctype, row["name"], schema, row)
					_write(row)
				last_name = rows[-1]["name"]


def emit_auth_rows(frappe, schemas):
	"""Stream credentials only through the private parent subprocess pipe.

	A backup may lack the encryption key matching historical ciphertext. Keep
	that ciphertext, explicitly marked unavailable, rather than dropping it.
	Never put either representation in reports, checkpoints, or error messages.
	"""
	from frappe.utils.password import get_decrypted_password

	for row in frappe.db.sql(
		"SELECT doctype, name, fieldname, password, encrypted FROM __Auth "
		"WHERE doctype IN %(doctypes)s ORDER BY doctype, name, fieldname",
		{"doctypes": tuple(sorted(schemas))}, as_dict=True,
	):
		row = dict(row)
		row["source_record_exists"] = bool(
			schemas[row["doctype"]].get("issingle")
			or frappe.db.exists(row["doctype"], row["name"])
		)
		row["decryptable"] = False
		if row.get("encrypted"):
			try:
				plaintext = get_decrypted_password(
					row["doctype"], row["name"], row["fieldname"], raise_exception=False
				)
			except Exception:
				plaintext = None
			if plaintext is not None:
				row["plaintext"] = plaintext
				row["decryptable"] = True
		_write(row)


def _fieldnames(schema):
	return [
		field["fieldname"]
		for field in schema.get("fields") or []
		if field.get("fieldname")
		and field.get("fieldtype") not in NO_VALUE_FIELD_TYPES
		and field.get("fieldtype") not in {"Table", "Table MultiSelect"}
	]


def _quote_identifier(value):
	return "`" + str(value).replace("`", "``") + "`"


def _table_fields(schema):
	return [
		field
		for field in schema.get("fields") or []
		if field.get("fieldtype") in {"Table", "Table MultiSelect"}
		and field.get("fieldname")
		and field.get("options")
	]


def _query_fields(frappe, doctype, schema):
	columns = set(frappe.db.get_table_columns(doctype))
	return [
		fieldname
		for fieldname in dict.fromkeys(list(SYSTEM_FIELDS) + _fieldnames(schema))
		if fieldname in columns
	]


def _password_fields(schema):
	return [
		field["fieldname"]
		for field in schema.get("fields") or []
		if field.get("fieldtype") == "Password" and field.get("fieldname")
	]


def _json_default(value):
	if isinstance(value, (datetime, date, time, Decimal)):
		return str(value)
	return str(value)


def _write(value):
	sys.stdout.write(json.dumps(value, separators=(",", ":"), default=_json_default) + "\n")
	sys.stdout.flush()


def _add_passwords(frappe, doctype, name, schema, row):
	from frappe.utils.password import get_decrypted_password

	passwords = {}
	for fieldname in _password_fields(schema):
		try:
			value = get_decrypted_password(
				doctype, name, fieldname, raise_exception=False
			)
		except Exception:
			value = None
		if value:
			passwords[fieldname] = value
	if passwords:
		row["__migration_passwords"] = passwords


def _add_runtime_passwords(frappe, doctype, name, row):
	from frappe.utils.password import get_decrypted_password

	passwords = {}
	for field in frappe.get_meta(doctype).fields:
		if field.fieldtype != "Password" or not field.fieldname:
			continue
		try:
			value = get_decrypted_password(
				doctype, name, field.fieldname, raise_exception=False
			)
		except Exception:
			value = None
		if value:
			passwords[field.fieldname] = value
	if passwords:
		row["__migration_passwords"] = passwords


def _emit_export_parent_rows(frappe, schemas, doctype, schema, rows):
	"""Emit complete parent documents for an already selected row batch."""

	if not rows:
		return
	by_name = {row["name"]: dict(row) for row in rows}
	parent_names = list(by_name)
	for table_field in _table_fields(schema):
		child_doctype = table_field["options"]
		child_schema = schemas.get(child_doctype)
		if not child_schema:
			raise RuntimeError(
				f"{doctype}.{table_field['fieldname']} uses unversioned child {child_doctype}"
			)
		children = frappe.get_all(
			child_doctype,
			filters={
				"parent": ["in", parent_names],
				"parenttype": doctype,
				"parentfield": table_field["fieldname"],
			},
			fields=_query_fields(frappe, child_doctype, child_schema),
			order_by="parent asc, idx asc, name asc",
			limit_page_length=0,
		)
		for child in children:
			child = dict(child)
			child["doctype"] = child_doctype
			by_name[child["parent"]].setdefault(table_field["fieldname"], []).append(child)
	for row in rows:
		data = by_name[row["name"]]
		data["doctype"] = doctype
		for table_field in _table_fields(schema):
			data.setdefault(table_field["fieldname"], [])
		_add_passwords(frappe, doctype, row["name"], schema, data)
		_write(data)


def export_doctype(
	frappe,
	schemas,
	doctype,
	batch_size,
	start_after=None,
	limit=None,
	names=None,
):
	if doctype not in schemas:
		raise RuntimeError(f"{doctype} is not a version-controlled Production API DocType")
	schema = schemas[doctype]
	if schema.get("istable"):
		raise RuntimeError(f"{doctype} is a child DocType and must be exported through its parent")
	if names is not None and (start_after or limit is not None):
		raise RuntimeError("Exact-name export cannot be combined with start_after/limit")
	if schema.get("issingle"):
		if names is not None and doctype not in set(names):
			return
		doc = frappe.get_single(doctype)
		row = doc.as_dict(no_nulls=False)
		row["doctype"] = doctype
		row["name"] = doctype
		_add_passwords(frappe, doctype, doctype, schema, row)
		_write(row)
		return
	if names is not None:
		requested = sorted({str(name) for name in names if name})
		for offset in range(0, len(requested), batch_size):
			chunk = requested[offset : offset + batch_size]
			rows = frappe.get_all(
				doctype,
				filters={"name": ["in", chunk]},
				fields=_query_fields(frappe, doctype, schema),
				order_by="name asc",
				limit_page_length=0,
			)
			_emit_export_parent_rows(frappe, schemas, doctype, schema, rows)
		return

	last_name = start_after or ""
	remaining = max(0, int(limit)) if limit is not None else None
	parent_fields = _query_fields(frappe, doctype, schema)
	while True:
		if remaining == 0:
			break
		filters = {"name": [">", last_name]} if last_name else None
		rows = frappe.get_all(
			doctype,
			filters=filters,
			fields=parent_fields,
			order_by="name asc",
			limit_page_length=min(batch_size, remaining) if remaining is not None else batch_size,
		)
		if not rows:
			break
		_emit_export_parent_rows(frappe, schemas, doctype, schema, rows)
		if remaining is not None:
			remaining -= len(rows)
		last_name = rows[-1]["name"]


def emit_resolved_identities(frappe, schemas, doctype, names):
	"""Resolve source identities, promoting child rows to their owning parents."""

	if doctype not in schemas:
		raise RuntimeError(f"Cannot resolve undeclared source DocType {doctype}")
	schema = schemas[doctype]
	requested = sorted({str(name) for name in names if name})
	fields = ["name", "parent", "parenttype"] if schema.get("istable") else ["name"]
	for offset in range(0, len(requested), 500):
		rows = frappe.get_all(
			doctype,
			filters={"name": ["in", requested[offset : offset + 500]]},
			fields=fields,
			order_by="name asc",
			limit_page_length=0,
		)
		for row in rows:
			payload = {"source_doctype": doctype, "name": row.name}
			if schema.get("istable"):
				payload.update({"parent": row.parent, "parenttype": row.parenttype})
			_write(payload)


def audit_physical_field_coverage(frappe, schemas):
	"""Fail before reset/load if populated SQL fields are invisible to export.

	Runtime metadata can omit historical physical columns. Reviewed overlays
	cover known cases; an unfamiliar populated column must stop a deployment,
	not silently disappear because the latest DocType JSON no longer declares it.
	Only field identities/counts leave this check, never their values.
	"""

	numeric_types = {"int", "bigint", "smallint", "tinyint", "mediumint",
		"decimal", "double", "float", "bit"}
	undefined = []
	for doctype, schema in sorted(schemas.items()):
		known = set(_fieldnames(schema)) | set(SYSTEM_FIELDS)
		if schema.get("issingle"):
			rows = frappe.db.sql(
				"SELECT field, value FROM tabSingles WHERE doctype=%s", (doctype,)
			)
			for fieldname, value in rows:
				if fieldname not in known:
					undefined.append({"doctype": doctype, "field": fieldname,
						"material_values": int(value not in (None, ""))})
			continue
		columns = frappe.db.sql(
			"SELECT column_name, data_type FROM information_schema.columns "
			"WHERE table_schema=DATABASE() AND table_name=%s ORDER BY ordinal_position",
			("tab" + doctype,),
		)
		unknown = [(name, datatype) for name, datatype in columns if name not in known]
		if not unknown:
			continue
		conditions = []
		for fieldname, datatype in unknown:
			column = _quote_identifier(fieldname)
			condition = (f"COALESCE({column},0)<>0" if datatype in numeric_types
				else f"{column} IS NOT NULL AND CAST({column} AS CHAR)<>''")
			conditions.append(f"SUM(CASE WHEN {condition} THEN 1 ELSE 0 END)")
		counts = frappe.db.sql(
			f"SELECT {', '.join(conditions)} FROM {_quote_identifier('tab' + doctype)}"
		)[0]
		undefined.extend({"doctype": doctype, "field": name, "material_values": int(count or 0)}
			for (name, _datatype), count in zip(unknown, counts))
	blockers = [row for row in undefined if row["material_values"]]
	if blockers:
		raise RuntimeError("Populated source fields are absent from the export schema: " + "; ".join(
			f"{row['doctype']}.{row['field']} ({row['material_values']} values)" for row in blockers
		))
	return {"checked_doctypes": len(schemas), "undefined_empty_fields": undefined}


def retired_source_rows(frappe):
	for doctype in RETIRED_SOURCE_TABLES:
		if not frappe.db.table_exists(doctype):
			continue
		last_name = ""
		while True:
			rows = frappe.db.sql(
				f"SELECT * FROM {_quote_identifier('tab' + doctype)} WHERE name>%s ORDER BY name LIMIT 500",
				(last_name,), as_dict=True,
			)
			if not rows:
				break
			for row in rows:
				yield {"source_doctype": doctype, "row": dict(row)}
			last_name = rows[-1]["name"]
	# Attachments of a retired dashboard have no operational parent on the
	# target. Archive their original metadata and any available bytes as data,
	# without recreating that dashboard or its permissions.
	for row in frappe.db.sql(
		"SELECT * FROM tabFile WHERE attached_to_doctype IN %s ORDER BY name",
		(RETIRED_SOURCE_TABLES,), as_dict=True,
	):
		yield archive_file_row(frappe, row)


def archive_file_row(frappe, row):
	record = {"source_doctype": "File", "row": dict(row)}
	if row.get('is_folder'):
		return record
	_file_doc, path = _resolve_physical_file(frappe, row)
	if not path:
		record["blob_issue"] = "Source blob unavailable"
	else:
		if Path(path).stat().st_size > 8 * 1024 * 1024:
			raise RuntimeError("Archived attachment exceeds 8 MiB; review external archive storage before migration")
		with open(path, "rb") as handle:
			content = handle.read()
		if len(content) != int(row.get('file_size') or 0) or hashlib.md5(content).hexdigest() != row.get('content_hash'):
			record["blob_issue"] = "Source blob does not match its metadata"
		else:
			record["blob_base64"] = base64.b64encode(content).decode("ascii")
	return record


def framework_scope(frappe, schemas, related_names=None):
	helper = runpy.run_path(str(Path(__file__).with_name('f15_framework_archive.py')))
	spine_modules = frappe.get_all(
		'Module Def', filters={'app_name': 'spine'}, pluck='name'
	)
	spine_doctypes = (
		frappe.get_all('DocType', filters={'module': ('in', spine_modules)}, pluck='name')
		if spine_modules else []
	)
	scope = helper['build_scope'](frappe, schemas, RETIRED_SOURCE_TABLES,
		related_names if related_names is not None else related_business_master_names(frappe, schemas),
		app_file_names=[row.name for row in _migration_files(frappe, schemas)],
		excluded_types=spine_doctypes)
	return helper, scope


def emit_framework_rows(frappe, schemas):
	helper, scope = framework_scope(frappe, schemas)
	for doctype, row in helper['iter_rows'](frappe, scope):
		_write(archive_file_row(frappe, row) if doctype == 'File' else
			{'source_doctype': doctype, 'row': row})
	for record in iter_approved_frappe_exact_archive_records(frappe):
		_write(record)


def emit_status(frappe, schemas, source_site):
	physical_coverage = audit_physical_field_coverage(frappe, schemas)
	approved_frappe_data = approved_frappe_census(frappe)
	approved_frappe_exact_archive = approved_frappe_exact_archive_census(frappe)
	related_names = related_business_master_names(frappe, schemas)
	framework, framework_selection = framework_scope(frappe, schemas, related_names)
	framework_census = framework['census'](frappe, framework_selection)
	framework_census.update(approved_frappe_exact_archive["tables"])
	related_digest = hashlib.sha256()
	for doctype, names in sorted(related_names.items()):
		for name in names:
			related_digest.update(json.dumps(
				_supporting_document(frappe, doctype, name),
				sort_keys=True, separators=(",", ":"), default=_json_default,
			).encode())
	for table, field in (("__Auth", "doctype"),):
		physical_table = "__Auth" if table == "__Auth" else "tabFile"
		count = frappe.db.sql(
			f"SELECT COUNT(*) FROM {_quote_identifier(physical_table)} WHERE {_quote_identifier(field)} IN %s",
			(RETIRED_SOURCE_TABLES,),
		)[0][0]
		if count:
			raise RuntimeError(f"Retired source tables have {count} {table} records; add an explicit preservation route before migration")
	retired_digest = hashlib.sha256()
	retired_counts = {}
	for record in retired_source_rows(frappe):
		retired_counts[record["source_doctype"]] = retired_counts.get(record["source_doctype"], 0) + 1
		retired_digest.update(json.dumps(record, sort_keys=True, default=_json_default).encode())
	parent_counts = {}
	table_counts = {}
	modified = {}
	for doctype, schema in sorted(schemas.items()):
		count = 1 if schema.get("issingle") else frappe.db.count(doctype)
		table_counts[doctype] = count
		if not schema.get("istable"):
			parent_counts[doctype] = count
		if schema.get("issingle"):
			modified[doctype] = None
		else:
			modified[doctype] = frappe.db.get_value(
				doctype, {}, "max(modified)"
			)
	schema_payload = json.dumps(
		schemas, sort_keys=True, separators=(",", ":"), default=_json_default
	)
	snapshot_payload = {
		"site": source_site,
		"approved_frappe_data": approved_frappe_data,
		"approved_frappe_exact_archive": approved_frappe_exact_archive,
		"physical_field_coverage": physical_coverage,
		"related_business_master_counts": {key: len(value) for key, value in related_names.items()},
		"related_business_master_fingerprint": related_digest.hexdigest(),
		"framework_records": framework_census,
		"file_metadata_fingerprint": hashlib.sha256(json.dumps(
			_migration_files(frappe, schemas), sort_keys=True, default=_json_default,
			separators=(',', ':'),
		).encode()).hexdigest(),
		"file_reference_fingerprint": hashlib.sha256(json.dumps(
			_file_reference_map(frappe, schemas), sort_keys=True, default=_json_default,
			separators=(',', ':'),
		).encode()).hexdigest(),
		"retired_table_counts": retired_counts,
		"retired_table_fingerprint": retired_digest.hexdigest(),
		"doctype_counts": parent_counts,
		"table_counts": table_counts,
		"max_modified": {key: str(value or "") for key, value in modified.items()},
		"schema_fingerprint": hashlib.sha256(
			schema_payload.encode("utf-8")
		).hexdigest(),
		# Single and credential edits do not reliably update a normal parent row.
		"single_fingerprint": hashlib.sha256(json.dumps(frappe.db.sql(
			"SELECT doctype, field, value FROM tabSingles WHERE doctype IN %(names)s "
			"ORDER BY doctype, field", {"names": tuple(sorted(schemas))}
		), default=_json_default, separators=(",", ":")).encode()).hexdigest(),
		"auth_fingerprint": hashlib.sha256(json.dumps(frappe.db.sql(
			"SELECT doctype, name, fieldname, password, encrypted FROM __Auth "
			"WHERE doctype IN %(names)s ORDER BY doctype, name, fieldname",
			{"names": tuple(sorted(schemas))}
		), default=_json_default, separators=(",", ":")).encode()).hexdigest(),
	}
	_write(
		{
			**snapshot_payload,
			"snapshot_fingerprint": hashlib.sha256(
				json.dumps(
					snapshot_payload, sort_keys=True, separators=(",", ":")
				).encode("utf-8")
			).hexdigest(),
			"maintenance_mode": bool(frappe.conf.get("maintenance_mode")),
			"total_parent_records": sum(parent_counts.values())
			+ int(approved_frappe_data["total"]),
		}
	)


def _collect_reference_names(value):
	"""Return Cut Bundle Movement Ledger names embedded in CPM JSON."""

	names = set()
	stack = [value]
	while stack:
		current = stack.pop()
		if isinstance(current, dict):
			for key, child in current.items():
				if key.endswith("_ref_docname") and child:
					names.add(str(child))
				else:
					stack.append(child)
		elif isinstance(current, list):
			stack.extend(current)
	return names


def emit_reference_data(frappe):
	"""Stream authoritative master/default values needed by F16 derivations."""

	default_received_type = frappe.db.get_single_value(
		"Stock Settings", "default_received_type"
	)
	default_packing_process = frappe.db.get_single_value(
		"IPD Settings", "default_packing_process"
	)
	root_item_groups = frappe.get_all(
		"Item Group",
		filters={"is_group": 1, "parent_item_group": ["in", (None, "")]},
		pluck="name",
		limit_page_length=0,
	)
	received_via_values = [
		row[0]
		for row in frappe.db.sql(
			"SELECT DISTINCT `received_via` FROM `tabVendor Bill Tracking` "
			"WHERE COALESCE(`received_via`, '')<>'' ORDER BY `received_via`"
		)
	]
	_write(
		{
			"kind": "migration_defaults",
			"default_received_type": default_received_type,
			"default_packing_process": default_packing_process,
			"root_item_groups": sorted(set(root_item_groups)),
			"bill_received_via": sorted({str(value) for value in received_via_values if value}),
		}
	)

	for row in frappe.get_all(
		"Item", fields=["name", "item_group", "default_unit_of_measure"], limit_page_length=0
	):
		_write(
			{
				"kind": "item",
				"name": row.name,
				"item_group": row.item_group,
				"default_uom": row.default_unit_of_measure,
			}
		)
	for row in frappe.get_all(
		"Item Attribute Value",
		fields=["name", "attribute_name", "attribute_value"],
		limit_page_length=0,
	):
		_write(
			{
				"kind": "item_attribute_value",
				"name": row.name,
				"attribute_name": row.attribute_name,
				"attribute_value": row.attribute_value,
			}
		)
	_emit_reference_variants_and_cut_panels(frappe)


def _file_reference_map(frappe, schemas):
	"""Find actual app field references, even when File's owner is blank."""
	files = frappe.get_all('File', filters={'is_folder': 0}, fields=['name', 'file_url'], limit_page_length=0)
	by_name = {row.name: [row.name] for row in files}
	by_url = {}
	for row in files:
		if row.file_url:
			by_url.setdefault(row.file_url, []).append(row.name)
	result = {}
	for doctype, schema in sorted(schemas.items()):
		for field in schema.get('fields') or []:
			fieldtype, fieldname = field.get('fieldtype'), field.get('fieldname')
			if fieldtype not in {'Attach', 'Attach Image'} and not (fieldtype == 'Link' and field.get('options') == 'File'):
				continue
			if schema.get('issingle'):
				rows = frappe.db.sql('SELECT %s AS name,value FROM tabSingles WHERE doctype=%s AND field=%s',
					(doctype, doctype, fieldname), as_dict=True)
			else:
				rows = frappe.db.sql(f'SELECT name,{_quote_identifier(fieldname)} AS value '
					f'FROM {_quote_identifier("tab" + doctype)} WHERE COALESCE({_quote_identifier(fieldname)},\'\')<>\'\' '
					'ORDER BY name', as_dict=True)
			for row in rows:
				for file_id in (by_name if fieldtype == 'Link' else by_url).get(row.value, []):
					result.setdefault(file_id, []).append({'doctype': doctype, 'name': row.name,
						'fieldname': fieldname, 'fieldtype': fieldtype})
	return result


def _migration_files(frappe, schemas, names=None):
	"""Select app-owned attachments and exact app Attach/Link File references."""

	if names is not None:
		names = sorted({str(name) for name in names if name})
		if not names:
			return []
	filters = {"is_folder": 0}
	if names is not None:
		filters["name"] = ["in", names]
	return frappe.get_all(
		"File",
		filters=filters,
		or_filters={'attached_to_doctype': ['in', sorted(schemas)],
			'name': ['in', sorted(_file_reference_map(frappe, schemas)) or ['']]},
		fields=['*'],
		order_by="name asc",
		limit_page_length=0,
	)


def emit_file_status(frappe, schemas, source_site, names=None):
	rows = _migration_files(frappe, schemas, names=names)
	orphans = [
		row
		for row in rows
		if not row.attached_to_doctype or not row.attached_to_name
		or not frappe.db.exists(row.attached_to_doctype, row.attached_to_name)
	]
	unique_content = {
		(row.content_hash, int(row.is_private or 0)): int(row.file_size or 0)
		for row in rows
	}
	_write(
		{
			"site": source_site,
			"file_count": len(rows),
			"file_bytes": sum(int(row.file_size or 0) for row in rows),
			"unique_content_count": len(unique_content),
			"unique_content_bytes": sum(unique_content.values()),
			"max_file_size": max((int(row.file_size or 0) for row in rows), default=0),
			"orphan_attachment_count": len(orphans),
			"orphan_attachment_bytes": sum(int(row.file_size or 0) for row in orphans),
		}
	)


def _resolve_physical_file(frappe, row):
	candidates = [row['name']]
	if row.get('content_hash'):
		candidates.extend(
			name
			for name in frappe.get_all(
				"File",
				filters={
					"content_hash": row['content_hash'],
					"is_private": int(row.get('is_private') or 0),
				},
				pluck="name",
				limit_page_length=0,
			)
			if name != row['name']
		)
	fallback = (None, None)
	for name in candidates:
		file_doc = frappe.get_doc("File", name)
		path = file_doc.get_full_path()
		if os.path.isfile(path):
			if fallback[0] is None:
				fallback = (file_doc, path)
			if row.get('content_hash') and os.path.getsize(path) == int(row.get('file_size') or 0):
				digest = hashlib.md5()
				with open(path, 'rb') as handle:
					for chunk in iter(lambda: handle.read(1024 * 1024), b''):
						digest.update(chunk)
				if digest.hexdigest() == row['content_hash']:
					return file_doc, path
	# Return an existing corrupt candidate only if no matching duplicate exists,
	# so the caller can report corruption separately from an absent blob.
	return fallback


def emit_file_health(frappe, schemas, names=None):
	for row in _migration_files(frappe, schemas, names=names):
		file_doc, path = _resolve_physical_file(frappe, row)
		if not path:
			_write(
				{
					"name": row.name,
					"file_name": row.file_name,
					"file_url": row.file_url,
					"file_size": row.file_size,
					"content_hash": row.content_hash,
					"is_private": row.is_private,
					"attached_to_doctype": row.attached_to_doctype,
					"attached_to_name": row.attached_to_name,
					"status": "missing",
				}
			)
		elif file_doc.name != row.name:
			_write(
				{
					"name": row.name,
					"status": "recovered_from_duplicate",
					"recovery_file": file_doc.name,
				}
			)
		else:
			with open(path, "rb") as handle:
				content = handle.read()
			actual_hash = hashlib.md5(content).hexdigest()
			if row.content_hash and actual_hash != row.content_hash:
				_write(
					{
						"name": row.name,
						"file_name": row.file_name,
						"status": "hash_mismatch",
						"metadata_hash": row.content_hash,
						"actual_hash": actual_hash,
					}
				)
			elif row.file_size is not None and len(content) != int(row.file_size):
				_write(
					{
						"name": row.name,
						"file_name": row.file_name,
						"status": "size_mismatch",
						"metadata_size": int(row.file_size),
						"actual_size": len(content),
					}
				)


def emit_files(
	frappe,
	schemas,
	start_after=None,
	metadata_only=False,
	names=None,
	allow_missing=False,
):
	"""Stream attachment metadata and each physical blob at most once.

	Rows before ``start_after`` are still visited to seed ``seen_content``. This
	keeps a resumed stream compact while allowing the target to reuse the blob
	already created by the prior checkpoint.
	"""

	seen_content = set()
	unavailable_content = set()
	references = _file_reference_map(frappe, schemas)
	for row in _migration_files(frappe, schemas, names=names):
		content_key = (row.content_hash, int(row.is_private or 0))
		include_content = not metadata_only and content_key not in seen_content
		seen_content.add(content_key)
		if start_after and row.name <= start_after:
			# Rebuild the availability state for content keys whose first row was
			# already checkpointed. Without this, a later duplicate can be emitted
			# with neither content nor missing_blob after a resume.
			if include_content:
				file_doc, path = _resolve_physical_file(frappe, row)
				blob_issue = None
				if not path:
					blob_issue = "no physical blob and no same-hash duplicate"
				else:
					with open(path, "rb") as handle:
						content = handle.read()
					actual_hash = hashlib.md5(content).hexdigest()
					if row.content_hash and actual_hash != row.content_hash:
						blob_issue = (
							f"content hash mismatch: metadata={row.content_hash}, disk={actual_hash}"
						)
					elif row.file_size is not None and len(content) != int(row.file_size):
						blob_issue = (
							f"size mismatch: metadata={row.file_size}, disk={len(content)}"
						)
				if blob_issue:
					if not allow_missing:
						raise RuntimeError(f"File {row.name} {blob_issue}")
					unavailable_content.add(content_key)
			continue
		payload = dict(row)
		payload['source_file_metadata'] = dict(row)
		payload['app_references'] = references.get(row.name, [])
		payload["kind"] = "file"
		if not row.attached_to_doctype or not row.attached_to_name or not frappe.db.exists(row.attached_to_doctype, row.attached_to_name):
			payload["orphan_attachment"] = 1
		if include_content:
			file_doc, path = _resolve_physical_file(frappe, row)
			if not path:
				if not allow_missing:
					raise RuntimeError(
						f"File {row.name} has no physical blob and no same-hash duplicate"
					)
				unavailable_content.add(content_key)
				payload["missing_blob"] = 1
			else:
				with open(path, "rb") as handle:
					content = handle.read()
				actual_hash = hashlib.md5(content).hexdigest()
				blob_issue = None
				if row.content_hash and actual_hash != row.content_hash:
					blob_issue = (
						f"content hash mismatch: metadata={row.content_hash}, disk={actual_hash}"
					)
				elif row.file_size is not None and len(content) != int(row.file_size):
					blob_issue = (
						f"size mismatch: metadata={row.file_size}, disk={len(content)}"
					)
				if blob_issue:
					if not allow_missing:
						raise RuntimeError(f"File {row.name} {blob_issue}")
					unavailable_content.add(content_key)
					payload["missing_blob"] = 1
					payload["blob_issue"] = blob_issue
				else:
					payload["content_base64"] = base64.b64encode(content).decode("ascii")
		elif content_key in unavailable_content:
			payload["missing_blob"] = 1
			payload["blob_issue"] = "same content key is unavailable"
		_write(payload)


def emit_stock_summary(frappe, source_site, dimensions):
	"""Emit a deterministic current-balance digest for every stock bucket."""

	dimensions = [str(fieldname) for fieldname in dimensions]
	if any(not SAFE_FIELDNAME.fullmatch(fieldname) for fieldname in dimensions):
		raise RuntimeError("Stock summary received an unsafe dimension fieldname")
	columns = set(frappe.db.get_table_columns("Stock Ledger Entry"))
	missing = [fieldname for fieldname in dimensions if fieldname not in columns]
	if missing:
		raise RuntimeError(
			"Source Stock Ledger Entry is missing target dimensions: "
			+ ", ".join(missing)
		)
	dimension_select = ", ".join(
		f"COALESCE({_quote_identifier(fieldname)}, '')" for fieldname in dimensions
	)
	group_fields = ", ".join(_quote_identifier(fieldname) for fieldname in dimensions)
	select_middle = f", {dimension_select}" if dimension_select else ""
	group_suffix = f", {group_fields}" if group_fields else ""
	digest = hashlib.sha256()
	total_qty = Decimal("0")
	total_value = Decimal("0")
	rows = frappe.db.sql(
		f"""
		SELECT item, warehouse{select_middle}, SUM(qty), SUM(stock_value_difference)
		FROM `tabStock Ledger Entry`
		WHERE COALESCE(is_cancelled, 0) = 0
		GROUP BY item, warehouse{group_suffix}
		ORDER BY item, warehouse{group_suffix}
		"""
	)
	for row in rows:
		item, warehouse = row[:2]
		dimension_values = row[2 : 2 + len(dimensions)]
		qty, stock_value = row[-2:]
		qty = Decimal(str(qty or 0)).quantize(Decimal("0.000000001"))
		stock_value = Decimal(str(stock_value or 0)).quantize(Decimal("0.000000001"))
		total_qty += qty
		total_value += stock_value
		payload = [
			item or "",
			warehouse or "",
			*[value or "" for value in dimension_values],
			format(qty, "f"),
			format(stock_value, "f"),
		]
		digest.update(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
		digest.update(b"\n")
	_write(
		{
			"site": source_site,
			"dimensions": dimensions,
			"bucket_count": len(rows),
			"bucket_digest": digest.hexdigest(),
			"total_qty": format(total_qty, "f"),
			"total_stock_value_difference": format(total_value, "f"),
		}
	)


def emit_broken_links(frappe, schemas):
	"""Stream every source-invalid Link value with its exact owning identity."""

	for doctype, schema in sorted(schemas.items()):
		if schema.get("issingle"):
			document = frappe.get_single(doctype)
			for field in schema.get("fields") or []:
				if field.get("fieldtype") not in {"Link", "Data"} or not field.get(
					"options"
				):
					continue
				if field.get("fieldtype") == "Data" and not frappe.db.exists(
					"DocType", field.get("options")
				):
					continue
				value = document.get(field.get("fieldname"))
				if value and not frappe.db.exists(field["options"], value):
					_write(
						{
							"source_doctype": doctype,
							"source_name": doctype,
							"fieldname": field.get("fieldname"),
							"link_doctype": field.get("options"),
							"value": value,
						}
					)
			continue
		columns = set(frappe.db.get_table_columns(doctype))
		for field in schema.get("fields") or []:
			fieldname = field.get("fieldname")
			link_doctype = field.get("options")
			if (
				field.get("fieldtype") not in {"Link", "Data"}
				or not fieldname
				or fieldname not in columns
				or not link_doctype
			):
				continue
			if field.get("fieldtype") == "Data" and not frappe.db.exists(
				"DocType", link_doctype
			):
				continue
			table = _quote_identifier("tab" + doctype)
			field_column = _quote_identifier(fieldname)
			if not frappe.db.exists("DocType", link_doctype):
				rows = frappe.db.sql(
					f"SELECT name, {field_column} FROM {table} "
					f"WHERE COALESCE({field_column}, '')<>''"
				)
			else:
				link_meta = frappe.get_meta(link_doctype)
				if link_meta.issingle:
					rows = frappe.db.sql(
						f"SELECT name, {field_column} FROM {table} "
						f"WHERE COALESCE({field_column}, '')<>'' AND {field_column}<>%s",
						(link_doctype,),
					)
				else:
					link_table = _quote_identifier("tab" + link_doctype)
					rows = frappe.db.sql(
						f"SELECT source.name, source.{field_column} FROM {table} source "
						f"LEFT JOIN {link_table} linked ON linked.name=source.{field_column} "
						f"WHERE COALESCE(source.{field_column}, '')<>'' AND linked.name IS NULL"
					)
			for source_name, value in rows:
				payload = {
						"source_doctype": doctype,
						"source_name": source_name,
						"fieldname": fieldname,
						"link_doctype": link_doctype,
						"value": value,
					}
				if schema.get("istable"):
					owner = frappe.db.get_value(
						doctype,
						source_name,
						["parent", "parenttype", "parentfield"],
						as_dict=True,
					) or {}
					payload.update(
						{
							"parent": owner.get("parent"),
							"parenttype": owner.get("parenttype"),
							"parentfield": owner.get("parentfield"),
						}
					)
				_write(payload)


def emit_series(frappe):
	"""Stream Frappe naming counters for a collision-safe target merge."""

	for row in frappe.db.sql(
		"SELECT `name`, `current` FROM `tabSeries` ORDER BY `name`",
		as_dict=True,
	):
		_write(
			{
				"name": row.name,
				"current": int(row.current or 0),
			}
		)


def emit_cut_bundle_edit_ledger_dependencies(frappe, names):
	"""Emit exact movement-ledger rows needed to open selected edit records."""

	requested = sorted({str(name) for name in names if name})
	if not requested or len(requested) > 250:
		raise RuntimeError("Cut Bundle Edit dependency requests require 1-250 names")
	placeholders = ", ".join(["%s"] * len(requested))
	edits = frappe.db.sql(
		"SELECT name, warehouse AS from_location, lot, "
		"TIMESTAMP(posting_date, posting_time) AS posting_datetime "
		"FROM `tabCut Bundle Edit` "
		f"WHERE name IN ({placeholders}) ORDER BY name",
		requested,
		as_dict=True,
	)
	returned = {str(row.name) for row in edits}
	missing = set(requested) - returned
	if missing:
		raise RuntimeError(
			"Missing Cut Bundle Edit dependency parents: "
			+ ", ".join(sorted(missing)[:20])
		)
	for edit in edits:
		rows = frappe.db.sql(
			"""
			SELECT cbml.name
			FROM `tabCut Bundle Movement Ledger` cbml
			INNER JOIN (
				SELECT cbm_key, MAX(posting_datetime) AS max_posting_datetime, lay_no
				FROM `tabCut Bundle Movement Ledger`
				WHERE posting_datetime <= %(posting_datetime)s
					AND is_cancelled = 0
					AND supplier = %(supplier)s
					AND lot = %(lot)s
					AND transformed = 0
				GROUP BY cbm_key
			) latest
				ON latest.cbm_key = cbml.cbm_key
				AND latest.max_posting_datetime = cbml.posting_datetime
			WHERE cbml.posting_datetime <= %(posting_datetime)s
				AND cbml.supplier = %(supplier)s
				AND cbml.lot = %(lot)s
			ORDER BY latest.lay_no, cbml.name
			""",
			{
				"posting_datetime": edit.posting_datetime,
				"supplier": edit.from_location,
				"lot": edit.lot,
			},
			as_dict=True,
		)
		for row in rows:
			_write(
				{
					"source_doctype": "Cut Bundle Movement Ledger",
					"name": row.name,
					"required_by": edit.name,
				}
			)


def emit_external_references(frappe, schemas):
	"""Stream unique Link values whose master is outside Production API."""

	for doctype, schema in sorted(schemas.items()):
		if schema.get("issingle"):
			doc = frappe.get_single(doctype)
			for field in schema.get("fields") or []:
				_field_external_reference(
					frappe, schemas, doctype, field, [(doctype, doc.get(field.get("fieldname")))]
				)
			continue
		columns = set(frappe.db.get_table_columns(doctype))
		for field in schema.get("fields") or []:
			fieldname = field.get("fieldname")
			if not fieldname or fieldname not in columns:
				continue
			fieldtype = field.get("fieldtype")
			if fieldtype == "Link":
				link_doctype = field.get("options")
				if not link_doctype or link_doctype in schemas or link_doctype == "File":
					continue
				table = _quote_identifier("tab" + doctype)
				column = _quote_identifier(fieldname)
				rows = frappe.db.sql(
					f"SELECT MIN(name), {column} FROM {table} "
					f"WHERE COALESCE({column}, '')<>'' GROUP BY {column}"
				)
				for source_name, value in rows:
					_write(
						{
							"source_doctype": doctype,
							"source_name": source_name,
							"fieldname": fieldname,
							"link_doctype": link_doctype,
							"value": value,
							"dynamic": False,
						}
					)
			elif fieldtype == "Dynamic Link" and field.get("options") in columns:
				table = _quote_identifier("tab" + doctype)
				column = _quote_identifier(fieldname)
				controller = _quote_identifier(field["options"])
				rows = frappe.db.sql(
					f"SELECT MIN(name), {controller}, {column} FROM {table} "
					f"WHERE COALESCE({controller}, '')<>'' AND COALESCE({column}, '')<>'' "
					f"GROUP BY {controller}, {column}"
				)
				for source_name, link_doctype, value in rows:
					if link_doctype in schemas or link_doctype == "File":
						continue
					_write(
						{
							"source_doctype": doctype,
							"source_name": source_name,
							"fieldname": fieldname,
							"link_doctype": link_doctype,
							"value": value,
							"dynamic": True,
						}
					)


def _field_external_reference(frappe, schemas, doctype, field, rows):
	fieldname = field.get("fieldname")
	if field.get("fieldtype") != "Link" or not fieldname:
		return
	link_doctype = field.get("options")
	if not link_doctype or link_doctype in schemas or link_doctype == "File":
		return
	for source_name, value in rows:
		if value:
			_write(
				{
					"source_doctype": doctype,
					"source_name": source_name,
					"fieldname": fieldname,
					"link_doctype": link_doctype,
					"value": value,
					"dynamic": False,
				}
			)


def related_business_master_names(frappe, schemas):
	"""Return the complete source Address and Contact inventories.

	These are business records in their own right. Restricting them to records
	referenced by Production API documents silently omits valid standalone or
	legacy contacts and addresses, so the original migration must load every
	source identity and its child rows.
	"""
	del schemas  # Kept in the signature for bridge-call compatibility.
	result = {
		doctype: {
			str(row.name)
			for row in frappe.db.sql(
				f"SELECT name FROM {_quote_identifier('tab' + doctype)} ORDER BY name",
				as_dict=True,
			)
		}
		for doctype in ("Address", "Contact")
	}

	# Every Address/Contact Dynamic Link child must still have a source parent.
	# The supporting-document export will include the complete child collection
	# for every valid parent below.
	for row in frappe.db.sql(
		"SELECT DISTINCT parenttype,parent FROM `tabDynamic Link` "
		"WHERE parenttype IN ('Address','Contact')",
		as_dict=True,
	):
		if str(row.parent) not in result[row.parenttype]:
			raise RuntimeError(f"Related Dynamic Link has missing {row.parenttype} parent {row.parent}; preserve this orphan explicitly before migration")

	# A Contact may select an Address directly, without a reverse Dynamic Link.
	# Fail closed if that source reference is already broken.
	if result["Contact"]:
		contact_addresses = {
			str(address)
			for address, in frappe.db.sql(
			"SELECT DISTINCT address FROM tabContact WHERE name IN %s AND COALESCE(address,'')<>''",
			(tuple(sorted(result["Contact"])),),
			)
		}
		if contact_addresses - result["Address"]:
			raise RuntimeError("A Contact selects a missing source Address; review before migration")
	return {key: sorted(value) for key, value in result.items()}


def _supporting_document(frappe, doctype, name):
	if doctype not in SUPPORTING_EXTERNAL_DOCTYPES:
		raise RuntimeError(f"Unsupported external supporting DocType {doctype}")
	if not frappe.db.exists(doctype, name):
		raise RuntimeError(f"Missing source {doctype} {name}")
	document = frappe.get_doc(doctype, name).as_dict(no_nulls=False)
	# Optional physical audit columns can be absent from live metadata. Keep
	# them, too; the target mapper must explicitly reject a populated omission.
	if doctype in {"Address", "Contact"}:
		physical = frappe.db.sql(
			f"SELECT * FROM {_quote_identifier('tab' + doctype)} WHERE name=%s",
			(name,), as_dict=True,
		)[0]
		document.update(dict(physical))
		for field in frappe.get_meta(doctype).get_table_fields():
			# Read every physical child column, not just fields still declared in
			# the current metadata. The target must reject any populated omission.
			document[field.fieldname] = [dict(row, doctype=field.options) for row in frappe.db.sql(
				f"SELECT * FROM {_quote_identifier('tab' + field.options)} "
				"WHERE parent=%s AND parenttype=%s AND parentfield=%s ORDER BY idx,name",
				(name, doctype, field.fieldname), as_dict=True,
			)]
	document["doctype"] = doctype
	_add_runtime_passwords(frappe, doctype, name, document)
	return document


def emit_supporting_documents(frappe, doctype, names):
	for name in names:
		_write(_supporting_document(frappe, doctype, name))


def _spine_doctypes(frappe):
	modules = frappe.get_all("Module Def", filters={"app_name": "spine"}, pluck="name")
	return set(
		frappe.get_all("DocType", filters={"module": ("in", modules)}, pluck="name")
		if modules
		else []
	)


def _approved_frappe_names(frappe, doctype, spine_doctypes):
	"""Return the reviewed live-record scope for one Frappe DocType."""

	if frappe.get_meta(doctype).issingle:
		return [doctype]
	filters = {}
	if doctype == "Dashboard Settings":
		filters["chart_config"] = ("!=", "")
	elif doctype == "DefaultValue":
		# Per-user defaults travel inside their User parent. This direct route is
		# only for the site-level __default collection.
		filters["parenttype"] = "__default"
	elif doctype == "Module Profile":
		# A User's Link must never be copied without its referenced profile.
		return sorted(
			{
				str(value)
				for value in frappe.get_all(
					"User",
					filters={"module_profile": ("is", "set")},
					pluck="module_profile",
					limit_page_length=0,
				)
				if value
			}
		)
	elif doctype == "List View Settings":
		filters["name"] = ("not in", tuple(sorted(spine_doctypes | {"Message Log"})))
	elif doctype == "Role":
		filters["name"] = ("!=", "Spine User")
	elif doctype == "Workspace":
		filters["public"] = 0
	return frappe.get_all(
		doctype,
		filters=filters,
		pluck="name",
		order_by="name asc",
		limit_page_length=0,
	)


def _approved_frappe_document(frappe, doctype, name, spine_doctypes, *, passwords):
	if frappe.get_meta(doctype).issingle:
		document = frappe.get_single(doctype).as_dict(no_nulls=False)
		document["name"] = doctype
	else:
		document = frappe.get_doc(doctype, name).as_dict(no_nulls=False)
	document["doctype"] = doctype

	for fieldname in REMOVED_FRAPPE_FIELDS.get(doctype, ()):
		document.pop(fieldname, None)
	if doctype == "User":
		document["roles"] = [
			row for row in document.get("roles") or [] if row.get("role") != "Spine User"
		]

	if passwords:
		_add_runtime_passwords(frappe, doctype, name, document)
	return document


def iter_approved_frappe_documents(frappe, *, passwords=True):
	"""Yield active Frappe data in dependency order with explicit exclusions."""

	spine_doctypes = _spine_doctypes(frappe)
	for doctype in APPROVED_FRAPPE_DATA_ORDER:
		for name in _approved_frappe_names(frappe, doctype, spine_doctypes):
			document = _approved_frappe_document(
				frappe, doctype, name, spine_doctypes, passwords=passwords
			)
			if doctype == "Custom DocPerm" and (
				document.get("role") == "Spine User"
				or document.get("parent") in spine_doctypes
				or document.get("parent") in RETIRED_SOURCE_TABLES
			):
				continue
			if doctype == "Email Unsubscribe" and document.get(
				"reference_doctype"
			) in spine_doctypes | {"Message Log"}:
				continue
			if doctype == "DefaultValue" and document.get(
				"defkey"
			) in UNSAFE_SYSTEM_DEFAULT_KEYS:
				continue
			for value in document.values():
				if not isinstance(value, list):
					continue
				for row in value:
					child_doctype = row.get("doctype") if isinstance(row, dict) else None
					if child_doctype and child_doctype not in APPROVED_FRAPPE_CHILD_DOCTYPES:
						raise RuntimeError(
							f"Unapproved Frappe child DocType {child_doctype} in {doctype}"
						)
			yield document


def approved_frappe_census(frappe):
	counts = {}
	child_counts = {}
	names = {}
	digest = hashlib.sha256()
	for document in iter_approved_frappe_documents(frappe, passwords=False):
		doctype = document["doctype"]
		counts[doctype] = counts.get(doctype, 0) + 1
		names.setdefault(doctype, []).append(str(document["name"]))
		for value in document.values():
			if not isinstance(value, list):
				continue
			for row in value:
				child_doctype = row.get("doctype") if isinstance(row, dict) else None
				if child_doctype:
					child_counts[child_doctype] = child_counts.get(child_doctype, 0) + 1
		digest.update(
			json.dumps(
				document,
				sort_keys=True,
				separators=(",", ":"),
				default=_json_default,
			).encode()
		)
		digest.update(b"\n")
	auth_digest = hashlib.sha256()
	auth_count = 0
	for doctype, record_names in sorted(names.items()):
		if not record_names:
			continue
		for row in frappe.db.sql(
			"SELECT doctype,name,fieldname,password,encrypted FROM __Auth "
			"WHERE doctype=%s AND name IN %s ORDER BY name,fieldname",
			(doctype, tuple(record_names)),
		):
			auth_digest.update(
				json.dumps(row, separators=(",", ":"), default=_json_default).encode()
			)
			auth_digest.update(b"\n")
			auth_count += 1
	return {
		"counts": counts,
		"child_counts": child_counts,
		"total": sum(counts.values()),
		"total_with_children": sum(counts.values()) + sum(child_counts.values()),
		"value_digest": digest.hexdigest(),
		"auth_count": auth_count,
		"auth_digest": auth_digest.hexdigest(),
	}


def _approved_frappe_exact_document(frappe, doctype, name):
	"""Return every physical source value for encrypted compatibility storage."""

	meta = frappe.get_meta(doctype)
	if meta.issingle:
		return {
			"doctype": doctype,
			"name": doctype,
			"single_values": [
				{"field": fieldname, "value": value}
				for fieldname, value in frappe.db.sql(
					"SELECT field,value FROM tabSingles WHERE doctype=%s ORDER BY field",
					(doctype,),
				)
			],
		}

	rows = frappe.db.sql(
		f"SELECT * FROM {_quote_identifier('tab' + doctype)} WHERE name=%s",
		(name,),
		as_dict=True,
	)
	if len(rows) != 1:
		raise RuntimeError(f"Approved Frappe source identity is missing: {doctype} {name}")
	document = dict(rows[0], doctype=doctype)
	for field in meta.get_table_fields():
		if getattr(field, "is_virtual", False) or not frappe.db.table_exists(field.options):
			continue
		document[field.fieldname] = [
			dict(row, doctype=field.options)
			for row in frappe.db.sql(
				f"SELECT * FROM {_quote_identifier('tab' + field.options)} "
				"WHERE parent=%s AND parenttype=%s AND parentfield=%s ORDER BY idx,name",
				(name, doctype, field.fieldname),
				as_dict=True,
			)
		]
	if doctype == "User" and isinstance(document.get("roles"), list):
		# All Spine data remains an explicit owner exclusion, including this role.
		document["roles"] = [
			row for row in document["roles"] if row.get("role") != "Spine User"
		]
	return document


def iter_approved_frappe_exact_archive_records(frappe):
	"""Yield a lossless encrypted companion for every approved Frappe record."""

	spine_doctypes = _spine_doctypes(frappe)
	selected_names = {}
	for doctype in (*APPROVED_FRAPPE_DATA_ORDER, *APPROVED_FRAPPE_ARCHIVE_ONLY_DOCTYPES):
		if not frappe.db.exists("DocType", doctype):
			continue
		names = (
			[doctype]
			if doctype in APPROVED_FRAPPE_ARCHIVE_ONLY_DOCTYPES
			else _approved_frappe_names(frappe, doctype, spine_doctypes)
		)
		for name in names:
			document = _approved_frappe_exact_document(frappe, doctype, name)
			if doctype == "Custom DocPerm" and (
				document.get("role") == "Spine User"
				or document.get("parent") in spine_doctypes
				or document.get("parent") in RETIRED_SOURCE_TABLES
			):
				continue
			if doctype == "Email Unsubscribe" and document.get(
				"reference_doctype"
			) in spine_doctypes | {"Message Log"}:
				continue
			selected_names.setdefault(doctype, []).append(str(name))
			yield {
				"archive_kind": "approved_frappe_exact",
				"source_doctype": APPROVED_FRAPPE_ARCHIVE_PREFIX + doctype,
				"row": document,
			}

	for doctype, names in sorted(selected_names.items()):
		if not names:
			continue
		for row in frappe.db.sql(
			"SELECT doctype,name,fieldname,password,encrypted FROM __Auth "
			"WHERE doctype=%s AND name IN %s ORDER BY name,fieldname",
			(doctype, tuple(names)),
			as_dict=True,
		):
			yield {
				"archive_kind": "approved_frappe_exact",
				"source_doctype": APPROVED_FRAPPE_ARCHIVE_PREFIX + "__Auth",
				"row": dict(row),
			}


def approved_frappe_exact_archive_census(frappe):
	counts = {}
	digest = hashlib.sha256()
	table_digests = {}
	for record in iter_approved_frappe_exact_archive_records(frappe):
		doctype = record["source_doctype"]
		counts[doctype] = counts.get(doctype, 0) + 1
		encoded = json.dumps(
			record,
			sort_keys=True,
			separators=(",", ":"),
			default=_json_default,
		).encode()
		digest.update(encoded)
		digest.update(b"\n")
		table_digests.setdefault(doctype, hashlib.sha256()).update(
			encoded
		)
		table_digests[doctype].update(b"\n")
	return {
		"counts": counts,
		"total": sum(counts.values()),
		"value_digest": digest.hexdigest(),
		"tables": {
			doctype: {
				"rows": count,
				"value_digest": table_digests[doctype].hexdigest(),
			}
			for doctype, count in counts.items()
		},
	}


def emit_approved_frappe_documents(frappe):
	for document in iter_approved_frappe_documents(frappe):
		_write(document)


def _emit_reference_variants_and_cut_panels(frappe):
	for row in frappe.get_all(
		"Item Variant", fields=["name", "item"], limit_page_length=0
	):
		_write({"kind": "item_variant", "name": row.name, "item": row.item})

	cut_panels = frappe.get_all(
		"Cut Panel Movement",
		fields=[
			"name",
			"against",
			"against_id",
			"cut_panel_movement_json",
			"from_warehouse",
		],
		limit_page_length=0,
	)
	cut_panels = [row for row in cut_panels if not row.from_warehouse]
	stock_entry_names = [
		row.against_id
		for row in cut_panels
		if row.against == "Stock Entry" and row.against_id
	]
	delivery_challan_names = [
		row.against_id
		for row in cut_panels
		if row.against == "Delivery Challan" and row.against_id
	]
	stock_entry_sources = {
		row.name: row.from_warehouse
		for row in frappe.get_all(
			"Stock Entry",
			filters={"name": ["in", stock_entry_names]},
			fields=["name", "from_warehouse"],
			limit_page_length=0,
		)
		if row.from_warehouse
	}
	delivery_challan_sources = {
		row.name: row.from_location
		for row in frappe.get_all(
			"Delivery Challan",
			filters={"name": ["in", delivery_challan_names]},
			fields=["name", "from_location"],
			limit_page_length=0,
		)
		if row.from_location
	}

	ledger_names_by_movement = {}
	all_ledger_names = set()
	for row in cut_panels:
		payload = row.cut_panel_movement_json
		if isinstance(payload, str) and payload:
			try:
				payload = json.loads(payload)
			except (TypeError, ValueError):
				payload = None
		names = _collect_reference_names(payload) if payload else set()
		ledger_names_by_movement[row.name] = names
		all_ledger_names.update(names)

	ledger_sources = {}
	all_ledger_names = list(all_ledger_names)
	for offset in range(0, len(all_ledger_names), 1000):
		for row in frappe.get_all(
			"Cut Bundle Movement Ledger",
			filters={"name": ["in", all_ledger_names[offset : offset + 1000]]},
			fields=["name", "supplier"],
			limit_page_length=0,
		):
			if row.supplier:
				ledger_sources[row.name] = row.supplier

	for row in cut_panels:
		candidates = {
			ledger_sources[name]
			for name in ledger_names_by_movement[row.name]
			if name in ledger_sources
		}
		if row.against == "Stock Entry" and row.against_id in stock_entry_sources:
			candidates.add(stock_entry_sources[row.against_id])
		elif (
			row.against == "Delivery Challan"
			and row.against_id in delivery_challan_sources
		):
			candidates.add(delivery_challan_sources[row.against_id])
		_write(
			{
				"kind": "cut_panel_from_warehouse",
				"name": row.name,
				"warehouse": next(iter(candidates)) if len(candidates) == 1 else None,
				"candidates": sorted(candidates),
			}
		)


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--source-bench", required=True)
	parser.add_argument("--source-site", required=True)
	parser.add_argument("--source-app", default="production_api")
	subparsers = parser.add_subparsers(dest="command", required=True)
	subparsers.add_parser("status")
	subparsers.add_parser("schemas")
	subparsers.add_parser("orphan-children")
	subparsers.add_parser("auth-rows")
	subparsers.add_parser("retired-rows")
	subparsers.add_parser("reference-data")
	subparsers.add_parser("related-business-masters")
	subparsers.add_parser("approved-frappe-data")
	subparsers.add_parser("approved-frappe-census")
	subparsers.add_parser("framework-rows")
	subparsers.add_parser("framework-census")
	file_status = subparsers.add_parser("file-status")
	file_status.add_argument("--names-json")
	file_health = subparsers.add_parser("file-health")
	file_health.add_argument("--names-json")
	stock_summary = subparsers.add_parser("stock-summary")
	stock_summary.add_argument("--dimensions-json", required=True)
	subparsers.add_parser("series")
	subparsers.add_parser("external-references")
	subparsers.add_parser("broken-links")
	exists = subparsers.add_parser("exists")
	exists.add_argument("--doctype", required=True)
	exists.add_argument("--name", required=True)
	files = subparsers.add_parser("files")
	files.add_argument("--start-after")
	files.add_argument("--metadata-only", action="store_true")
	files.add_argument("--names-json")
	files.add_argument("--allow-missing", action="store_true")
	supporting = subparsers.add_parser("supporting-documents")
	supporting.add_argument("--doctype", required=True)
	supporting.add_argument("--names-json", required=True)
	export = subparsers.add_parser("export")
	export.add_argument("--doctype", required=True)
	export.add_argument("--batch-size", type=int, default=500)
	export.add_argument("--start-after")
	export.add_argument("--limit", type=int)
	export.add_argument("--names-json")
	resolve = subparsers.add_parser("resolve-identities")
	resolve.add_argument("--doctype", required=True)
	resolve.add_argument("--names-json", required=True)
	cut_bundle_dependencies = subparsers.add_parser("cut-bundle-edit-ledgers")
	cut_bundle_dependencies.add_argument("--names-json", required=True)
	args = parser.parse_args()

	warnings.filterwarnings("ignore")
	import frappe

	if not SAFE_NAME.fullmatch(args.source_site) or not SAFE_NAME.fullmatch(args.source_app):
		raise RuntimeError("Unsafe source site or app name")
	source_bench = Path(args.source_bench)
	if not source_bench.is_absolute():
		raise RuntimeError("Source bench must be an absolute path")
	source_bench = source_bench.resolve()
	source_app_root = source_bench / "apps" / args.source_app / args.source_app
	supporting_schema_roots = (
		source_bench
		/ "apps"
		/ "frappe"
		/ "frappe"
		/ "core"
		/ "doctype"
		/ "sms_parameter",
		source_bench / "apps" / "frappe" / "frappe" / "core" / "doctype" / "sms_settings",
		# Only frappe_tools configuration enters the auxiliary one-pass migration.
		# Spine is installed on the target with clean defaults; none of its source
		# schemas are part of this contract.
		source_bench / "apps" / "frappe_tools" / "frappe_tools" / "frappe_tools"
		/ "doctype" / "document_scanner_settings",
		source_bench / "apps" / "frappe_tools" / "frappe_tools" / "frappe_tools"
		/ "doctype" / "document_scanner_settings_items",
		source_bench / "apps" / "frappe_tools" / "frappe_tools" / "frappe_tools"
		/ "doctype" / "document_scanner_server_setting",
		source_bench / "apps" / "frappe_tools" / "frappe_tools" / "frappe_tools"
		/ "doctype" / "log_file_downloader",
	)
	if not (source_bench / "sites" / args.source_site / "site_config.json").is_file():
		raise RuntimeError("Configured source site does not exist in the source bench")
	if not source_app_root.is_dir():
		raise RuntimeError("Configured source app is not installed in the source bench")
	missing_schema_roots = [str(path) for path in supporting_schema_roots if not path.is_dir()]
	if missing_schema_roots:
		raise RuntimeError(
			"Required source schema roots are unavailable: " + ", ".join(missing_schema_roots)
		)

	declared_schemas = _load_schemas(source_app_root, supporting_schema_roots)
	frappe.init(site=args.source_site, sites_path=str(source_bench / "sites"))
	frappe.connect()
	try:
		installed_apps = set(frappe.get_installed_apps())
		missing_apps = {args.source_app, "frappe_tools"} - installed_apps
		if missing_apps:
			raise RuntimeError(
				f"Required source apps {sorted(missing_apps)!r} are not installed on "
				f"{args.source_site!r}"
			)
		if args.command == "export":
			schemas = _load_export_schemas(frappe, declared_schemas, args.doctype)
		elif args.command in {
			"status",
			"schemas",
			"orphan-children",
			"auth-rows",
			"exists",
			"broken-links",
			"external-references",
			"related-business-masters",
			"approved-frappe-data",
			"approved-frappe-census",
			"framework-rows",
			"framework-census",
			"file-health",
			"file-status",
			"files",
		}:
			schemas = _load_runtime_schemas(frappe, declared_schemas)
		else:
			schemas = declared_schemas
		if args.command == "status":
			emit_status(frappe, schemas, args.source_site)
		elif args.command == "schemas":
			emit_schemas(schemas)
		elif args.command == "orphan-children":
			emit_orphan_children(frappe, schemas)
		elif args.command == "auth-rows":
			emit_auth_rows(frappe, schemas)
		elif args.command == "retired-rows":
			for record in retired_source_rows(frappe):
				_write(record)
		elif args.command == "reference-data":
			emit_reference_data(frappe)
		elif args.command == "file-status":
			emit_file_status(
				frappe,
				schemas,
				args.source_site,
				names=json.loads(args.names_json) if args.names_json else None,
			)
		elif args.command == "file-health":
			emit_file_health(
				frappe,
				schemas,
				names=json.loads(args.names_json) if args.names_json else None,
			)
		elif args.command == "stock-summary":
			emit_stock_summary(
				frappe,
				args.source_site,
				json.loads(args.dimensions_json),
			)
		elif args.command == "series":
			emit_series(frappe)
		elif args.command == "external-references":
			emit_external_references(frappe, schemas)
		elif args.command == "related-business-masters":
			for doctype, names in related_business_master_names(frappe, schemas).items():
				for name in names:
					_write({"doctype": doctype, "name": name})
		elif args.command == "approved-frappe-data":
			emit_approved_frappe_documents(frappe)
		elif args.command == "approved-frappe-census":
			_write(approved_frappe_census(frappe))
		elif args.command == "framework-rows":
			emit_framework_rows(frappe, schemas)
		elif args.command == "framework-census":
			helper, scope = framework_scope(frappe, schemas)
			census = helper['census'](frappe, scope)
			census.update(approved_frappe_exact_archive_census(frappe)["tables"])
			_write(census)
		elif args.command == "broken-links":
			emit_broken_links(frappe, schemas)
		elif args.command == "exists":
			if args.doctype not in schemas or schemas[args.doctype].get("istable"):
				raise RuntimeError("Exists checks require a declared parent DocType")
			_write(
				{
					"doctype": args.doctype,
					"name": args.name,
					"exists": bool(frappe.db.exists(args.doctype, args.name)),
				}
			)
		elif args.command == "resolve-identities":
			emit_resolved_identities(
				frappe,
				schemas,
				args.doctype,
				json.loads(args.names_json),
			)
		elif args.command == "cut-bundle-edit-ledgers":
			emit_cut_bundle_edit_ledger_dependencies(
				frappe,
				json.loads(args.names_json),
			)
		elif args.command == "supporting-documents":
			emit_supporting_documents(
				frappe,
				args.doctype,
				json.loads(args.names_json),
			)
		elif args.command == "files":
			emit_files(
				frappe,
				schemas,
				start_after=args.start_after,
				metadata_only=args.metadata_only,
				names=json.loads(args.names_json) if args.names_json else None,
				allow_missing=args.allow_missing,
			)
		else:
			export_doctype(
				frappe,
				schemas,
				args.doctype,
				max(1, min(args.batch_size, 2000)),
				args.start_after,
				args.limit,
				json.loads(args.names_json) if args.names_json else None,
			)
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
