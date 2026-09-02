#!/usr/bin/env python3
"""Read-only source/target value audit for the existing SD-YRP Spine sync.

The audit compares field values for records present on both sites. Parent
fields are compared by document name. Child tables are compared in ``idx``
order while ignoring child-row names, because a few approved compatibility
mappers intentionally regenerate child identities.

No Frappe APIs are loaded and neither database is modified.
"""

from __future__ import annotations

import argparse
import datetime as dt
import decimal
import json
from collections import defaultdict
from pathlib import Path

import pymysql
from pymysql.cursors import DictCursor


SYNC_DOCTYPES = (
	("Country", "Country"),
	("UOM", "YRP UOM"),
	("Brand", "YRP Brand"),
	("Terms and Condition", "YRP Terms and Condition"),
	("Product Season", "SD YRP Product Season"),
	("Product Category", "SD YRP Product Category"),
	("Additional Parameter Key", "YRP Additional Parameter Key"),
	("Additional Parameter Value", "YRP Additional Parameter Value"),
	("Item Attribute", "YRP Item Attribute"),
	("Production Term", "YRP Production Term"),
	("User", "User"),
	("Item Category", "YRP Item Category"),
	("Address", "Address"),
	("Item Group", "YRP Item Group"),
	("Item Attribute Value", "YRP Item Attribute Value"),
	("Department", "YRP Department"),
	("Contact", "Contact"),
	("Item Item Attribute Mapping", "YRP Item Item Attribute Mapping"),
	("Supplier", "YRP Supplier"),
	("Item", "YRP Item"),
	("Process", "YRP Process"),
	("Item Variant", "YRP Item Variant"),
	("Item Dependent Attribute Mapping", "YRP Item Dependent Attribute Mapping"),
	("Item BOM Attribute Mapping", "YRP Item BOM Attribute Mapping"),
	("IPD Settings", "SD YRP IPD Settings"),
	("MRP Settings", "SD YRP MRP Settings"),
	("Production Order", "YRP Production Order"),
	("Lot Template", "SD YRP Lot Template"),
	("Item Production Detail", "YRP Item Production Detail"),
	("IPD Compacting", "SD YRP IPD Compacting"),
	("Lot", "SD YRP Lot"),
)

TABLE_FIELD_TYPES = {"Table", "Table MultiSelect"}
NO_COLUMN_FIELD_TYPES = {
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Fold",
	"Heading",
}
EMPTY_VALUES = (None, "")


def _load_site_config(bench: Path, site: str) -> dict:
	common_path = bench / "sites" / "common_site_config.json"
	site_path = bench / "sites" / site / "site_config.json"
	common = json.loads(common_path.read_text()) if common_path.exists() else {}
	return {**common, **json.loads(site_path.read_text())}


def _connect(bench: Path, site: str):
	config = _load_site_config(bench, site)
	return pymysql.connect(
		host=config.get("db_host") or "127.0.0.1",
		port=int(config.get("db_port") or 3306),
		user=config["db_name"],
		password=config["db_password"],
		database=config["db_name"],
		charset="utf8mb4",
		cursorclass=DictCursor,
	)


def _quote(value: str) -> str:
	return "`" + value.replace("`", "``") + "`"


def _meta(connection, doctype: str) -> dict:
	fields = {}
	with connection.cursor() as cursor:
		cursor.execute(
			"""
			select fieldname, fieldtype, options, idx
			from `tabDocField`
			where parent = %s
			order by idx
			""",
			(doctype,),
		)
		for row in cursor.fetchall():
			if row["fieldname"]:
				fields[row["fieldname"]] = row

		cursor.execute(
			"""
			select fieldname, fieldtype, options, idx
			from `tabCustom Field`
			where dt = %s
			order by idx
			""",
			(doctype,),
		)
		for row in cursor.fetchall():
			if row["fieldname"]:
				fields[row["fieldname"]] = row

		cursor.execute(
			"select issingle, istable from `tabDocType` where name = %s",
			(doctype,),
		)
		doctype_row = cursor.fetchone() or {"issingle": 0, "istable": 0}

	return {
		"fields": fields,
		"issingle": int(doctype_row["issingle"] or 0),
		"istable": int(doctype_row["istable"] or 0),
	}


def _columns(connection, doctype: str) -> set[str]:
	with connection.cursor() as cursor:
		cursor.execute(
			"""
			select column_name
			from information_schema.columns
			where table_schema = database() and table_name = %s
			""",
			("tab" + doctype,),
		)
		return {row["column_name"] for row in cursor.fetchall()}


def _normalise(value):
	if value in EMPTY_VALUES:
		return None
	if isinstance(value, decimal.Decimal):
		return value.normalize()
	if isinstance(value, (dt.date, dt.time, dt.datetime)):
		return value.isoformat(sep=" ") if isinstance(value, dt.datetime) else value.isoformat()
	if isinstance(value, bytes):
		return value.decode(errors="replace")
	return value


def _is_meaningful(value, fieldtype: str) -> bool:
	value = _normalise(value)
	if value is None:
		return False
	if fieldtype in {"Check", "Int", "Float", "Currency", "Percent"}:
		try:
			return decimal.Decimal(str(value)) != 0
		except decimal.InvalidOperation:
			pass
	return True


def _regular_rows(connection, doctype: str, fields: list[str]) -> dict[str, dict]:
	columns = ["name", *fields]
	query = "select " + ", ".join(_quote(field) for field in columns)
	query += " from " + _quote("tab" + doctype)
	with connection.cursor() as cursor:
		cursor.execute(query)
		return {row["name"]: row for row in cursor.fetchall()}


def _single_values(connection, doctype: str) -> dict:
	with connection.cursor() as cursor:
		cursor.execute(
			"select field, value from `tabSingles` where doctype = %s",
			(doctype,),
		)
		return {row["field"]: row["value"] for row in cursor.fetchall()}


def _child_rows(
	connection,
	child_doctype: str,
	parenttype: str,
	parentfield: str,
	fields: list[str],
	parents: set[str],
) -> dict[str, list[tuple]]:
	if not parents:
		return {}
	columns = ["parent", "idx", *fields]
	query = "select " + ", ".join(_quote(field) for field in columns)
	query += " from " + _quote("tab" + child_doctype)
	query += " where parenttype = %s and parentfield = %s order by parent, idx"
	grouped = defaultdict(list)
	with connection.cursor() as cursor:
		cursor.execute(query, (parenttype, parentfield))
		for row in cursor.fetchall():
			if row["parent"] not in parents:
				continue
			grouped[row["parent"]].append(
				tuple(_normalise(row.get(field)) for field in fields)
			)
	return grouped


def _compare_parent_fields(
	source,
	target,
	source_doctype: str,
	target_doctype: str,
	source_meta: dict,
	target_meta: dict,
) -> dict:
	source_columns = _columns(source, source_doctype) if not source_meta["issingle"] else set()
	target_columns = _columns(target, target_doctype) if not target_meta["issingle"] else set()
	source_scalar = {
		name: field
		for name, field in source_meta["fields"].items()
		if field["fieldtype"] not in TABLE_FIELD_TYPES | NO_COLUMN_FIELD_TYPES
		and (source_meta["issingle"] or name in source_columns)
	}
	target_scalar = {
		name: field
		for name, field in target_meta["fields"].items()
		if field["fieldtype"] not in TABLE_FIELD_TYPES | NO_COLUMN_FIELD_TYPES
		and (target_meta["issingle"] or name in target_columns)
	}
	common_fields = sorted(set(source_scalar) & set(target_scalar))

	if source_meta["issingle"]:
		source_rows = {"__single__": _single_values(source, source_doctype)}
		target_rows = {"__single__": _single_values(target, target_doctype)}
	else:
		source_rows = _regular_rows(source, source_doctype, sorted(source_scalar))
		target_rows = _regular_rows(target, target_doctype, sorted(target_scalar))
	common_names = set(source_rows) & set(target_rows)

	mismatches = []
	for fieldname in common_fields:
		bad = [
			name
			for name in common_names
			if _normalise(source_rows[name].get(fieldname))
			!= _normalise(target_rows[name].get(fieldname))
		]
		if bad:
			mismatches.append(
				{
					"fieldname": fieldname,
					"mismatched_records": len(bad),
					"sample_names": sorted(bad)[:5],
				}
			)

	source_only = []
	for fieldname in sorted(set(source_scalar) - set(target_scalar)):
		field = source_scalar[fieldname]
		meaningful = [
			name
			for name, row in source_rows.items()
			if _is_meaningful(row.get(fieldname), field["fieldtype"])
		]
		if meaningful:
			source_only.append(
				{
					"fieldname": fieldname,
					"fieldtype": field["fieldtype"],
					"populated_records": len(meaningful),
					"sample_names": sorted(meaningful)[:5],
				}
			)

	return {
		"common_records": len(common_names),
		"field_mismatches": mismatches,
		"populated_source_only_fields": source_only,
		"common_names": common_names,
	}


def _compare_child_tables(
	source,
	target,
	source_doctype: str,
	target_doctype: str,
	source_meta: dict,
	target_meta: dict,
	common_names: set[str],
) -> list[dict]:
	results = []
	source_tables = {
		name: field
		for name, field in source_meta["fields"].items()
		if field["fieldtype"] in TABLE_FIELD_TYPES and field.get("options")
	}
	target_tables = {
		name: field
		for name, field in target_meta["fields"].items()
		if field["fieldtype"] in TABLE_FIELD_TYPES and field.get("options")
	}

	for fieldname, source_field in source_tables.items():
		target_field = target_tables.get(fieldname)
		if not target_field:
			continue
		source_child = source_field["options"]
		target_child = target_field["options"]
		source_child_meta = _meta(source, source_child)
		target_child_meta = _meta(target, target_child)
		source_columns = _columns(source, source_child)
		target_columns = _columns(target, target_child)
		source_scalar = {
			name: field
			for name, field in source_child_meta["fields"].items()
			if field["fieldtype"] not in TABLE_FIELD_TYPES | NO_COLUMN_FIELD_TYPES
			and name in source_columns
		}
		target_scalar = {
			name: field
			for name, field in target_child_meta["fields"].items()
			if field["fieldtype"] not in TABLE_FIELD_TYPES | NO_COLUMN_FIELD_TYPES
			and name in target_columns
		}
		common_fields = sorted(set(source_scalar) & set(target_scalar))
		source_rows = _child_rows(
			source, source_child, source_doctype, fieldname, common_fields, common_names
		)
		target_rows = _child_rows(
			target, target_child, target_doctype, fieldname, common_fields, common_names
		)
		bad = [
			name
			for name in common_names
			if source_rows.get(name, []) != target_rows.get(name, [])
		]

		source_only_fields = []
		for child_fieldname in sorted(set(source_scalar) - set(target_scalar)):
			field = source_scalar[child_fieldname]
			rows = _child_rows(
				source,
				source_child,
				source_doctype,
				fieldname,
				[child_fieldname],
				common_names,
			)
			populated = sum(
				1
				for parent_rows in rows.values()
				for row in parent_rows
				if _is_meaningful(row[0], field["fieldtype"])
			)
			if populated:
				source_only_fields.append(
					{
						"fieldname": child_fieldname,
						"fieldtype": field["fieldtype"],
						"populated_rows": populated,
					}
				)

		if bad or source_only_fields:
			results.append(
				{
					"fieldname": fieldname,
					"source_child_doctype": source_child,
					"target_child_doctype": target_child,
					"compared_fields": common_fields,
					"mismatched_parents": len(bad),
					"source_rows": sum(len(rows) for rows in source_rows.values()),
					"target_rows": sum(len(rows) for rows in target_rows.values()),
					"sample_parents": sorted(bad)[:5],
					"populated_source_only_fields": source_only_fields,
				}
			)

	for fieldname, source_field in source_tables.items():
		if fieldname in target_tables:
			continue
		source_child = source_field["options"]
		rows = _child_rows(source, source_child, source_doctype, fieldname, [], common_names)
		row_count = sum(len(parent_rows) for parent_rows in rows.values())
		if row_count:
			results.append(
				{
					"fieldname": fieldname,
					"source_child_doctype": source_child,
					"target_child_doctype": None,
					"source_rows": row_count,
					"target_rows": 0,
					"mismatched_parents": len(rows),
					"sample_parents": sorted(rows)[:5],
				}
			)

	return results


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--source-bench", type=Path, required=True)
	parser.add_argument("--source-site", required=True)
	parser.add_argument("--target-bench", type=Path, required=True)
	parser.add_argument("--target-site", required=True)
	parser.add_argument("--doctypes-json")
	args = parser.parse_args()
	requested = tuple(json.loads(args.doctypes_json)) if args.doctypes_json else SYNC_DOCTYPES
	target_by_source = dict(SYNC_DOCTYPES)
	doctypes = tuple(
		(
			tuple(row)
			if isinstance(row, (list, tuple)) and len(row) == 2
			else (row, target_by_source.get(row, row))
		)
		for row in requested
	)

	source = _connect(args.source_bench.resolve(), args.source_site)
	target = _connect(args.target_bench.resolve(), args.target_site)
	try:
		results = []
		for source_doctype, target_doctype in doctypes:
			source_meta = _meta(source, source_doctype)
			target_meta = _meta(target, target_doctype)
			parent = _compare_parent_fields(
				source,
				target,
				source_doctype,
				target_doctype,
				source_meta,
				target_meta,
			)
			children = _compare_child_tables(
				source,
				target,
				source_doctype,
				target_doctype,
				source_meta,
				target_meta,
				parent.pop("common_names"),
			)
			if parent["field_mismatches"] or parent["populated_source_only_fields"] or children:
				results.append(
					{
						"source_doctype": source_doctype,
						"target_doctype": target_doctype,
						**parent,
						"child_table_mismatches": children,
					}
				)
		print(json.dumps(results, indent=2, default=str))
	finally:
		source.close()
		target.close()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
