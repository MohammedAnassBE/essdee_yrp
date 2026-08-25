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
	"Email Account",
	"Letter Head",
	"Print Format",
	"Role",
	"User",
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
	return {
		"doctype": "DocType",
		"name": doctype,
		"module": getattr(meta, "module", None) or declared.get("module"),
		"istable": int(bool(getattr(meta, "istable", declared.get("istable")))),
		"issingle": int(bool(getattr(meta, "issingle", declared.get("issingle")))),
		"autoname": getattr(meta, "autoname", None) or declared.get("autoname"),
		"fields": [field.as_dict() for field in meta.fields],
	}


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


def export_doctype(frappe, schemas, doctype, batch_size, start_after=None, limit=None):
	if doctype not in schemas:
		raise RuntimeError(f"{doctype} is not a version-controlled Production API DocType")
	schema = schemas[doctype]
	if schema.get("istable"):
		raise RuntimeError(f"{doctype} is a child DocType and must be exported through its parent")
	if schema.get("issingle"):
		doc = frappe.get_single(doctype)
		row = doc.as_dict(no_nulls=False)
		row["doctype"] = doctype
		row["name"] = doctype
		_add_passwords(frappe, doctype, doctype, schema, row)
		_write(row)
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
		if remaining is not None:
			remaining -= len(rows)
		last_name = rows[-1]["name"]


def emit_status(frappe, schemas, source_site):
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
		"doctype_counts": parent_counts,
		"table_counts": table_counts,
		"max_modified": {key: str(value or "") for key, value in modified.items()},
		"schema_fingerprint": hashlib.sha256(
			schema_payload.encode("utf-8")
		).hexdigest(),
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
			"total_parent_records": sum(parent_counts.values()),
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
	_emit_reference_variants_and_cut_panels(frappe)


def _migration_files(frappe, schemas, names=None):
	"""Return only attachments owned by version-controlled source DocTypes."""

	if names is not None:
		names = sorted({str(name) for name in names if name})
		if not names:
			return []
	filters = {
		"is_folder": 0,
		"attached_to_doctype": ["in", sorted(schemas)],
	}
	if names is not None:
		filters["name"] = ["in", names]
	return frappe.get_all(
		"File",
		filters=filters,
		fields=[
			"name",
			"file_name",
			"file_url",
			"file_size",
			"content_hash",
			"is_private",
			"attached_to_doctype",
			"attached_to_name",
			"attached_to_field",
			"owner",
			"creation",
			"modified",
			"modified_by",
		],
		order_by="name asc",
		limit_page_length=0,
	)


def emit_file_status(frappe, schemas, source_site, names=None):
	rows = _migration_files(frappe, schemas, names=names)
	orphans = [
		row
		for row in rows
		if not frappe.db.exists(row.attached_to_doctype, row.attached_to_name)
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
	candidates = [row.name]
	if row.content_hash:
		candidates.extend(
			name
			for name in frappe.get_all(
				"File",
				filters={
					"content_hash": row.content_hash,
					"is_private": int(row.is_private or 0),
				},
				pluck="name",
				limit_page_length=0,
			)
			if name != row.name
		)
	for name in candidates:
		file_doc = frappe.get_doc("File", name)
		path = file_doc.get_full_path()
		if os.path.isfile(path):
			return file_doc, path
	return None, None


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
		payload["kind"] = "file"
		if not frappe.db.exists(row.attached_to_doctype, row.attached_to_name):
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
				_write(
					{
						"source_doctype": doctype,
						"source_name": source_name,
						"fieldname": fieldname,
						"link_doctype": link_doctype,
						"value": value,
					}
				)


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


def emit_supporting_documents(frappe, doctype, names):
	if doctype not in SUPPORTING_EXTERNAL_DOCTYPES:
		raise RuntimeError(f"Unsupported external supporting DocType {doctype}")
	for name in names:
		if not frappe.db.exists(doctype, name):
			raise RuntimeError(f"Missing source {doctype} {name}")
		document = frappe.get_doc(doctype, name).as_dict(no_nulls=False)
		document["doctype"] = doctype
		_add_runtime_passwords(frappe, doctype, name, document)
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
	subparsers.add_parser("reference-data")
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
	)
	if not (source_bench / "sites" / args.source_site / "site_config.json").is_file():
		raise RuntimeError("Configured source site does not exist in the source bench")
	if not source_app_root.is_dir():
		raise RuntimeError("Configured source app is not installed in the source bench")

	declared_schemas = _load_schemas(source_app_root, supporting_schema_roots)
	frappe.init(site=args.source_site, sites_path=str(source_bench / "sites"))
	frappe.connect()
	try:
		if args.source_app not in frappe.get_installed_apps():
			raise RuntimeError(
				f"Configured source app {args.source_app!r} is not installed on "
				f"{args.source_site!r}"
			)
		if args.command == "export":
			schemas = _load_export_schemas(frappe, declared_schemas, args.doctype)
		elif args.command in {
			"status",
			"schemas",
			"exists",
			"broken-links",
			"external-references",
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
			)
	finally:
		frappe.destroy()


if __name__ == "__main__":
	main()
