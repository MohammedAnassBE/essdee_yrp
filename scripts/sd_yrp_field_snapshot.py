#!/usr/bin/env python3
"""Read-only runtime metadata/data probe for the SD-YRP field parity audit.

This helper is intentionally standalone so the Frappe-15 and Frappe-16 Python
environments can execute the same code against their own site metadata. It
never commits or mutates either site.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import deque
from pathlib import Path


TABLE_FIELD_TYPES = {"Table", "Table MultiSelect"}


def _connect(bench: Path, site: str):
	sys.path.insert(0, str(bench / "apps" / "frappe"))
	os.chdir(bench)
	import frappe

	frappe.init(site=site, sites_path=str(bench / "sites"))
	frappe.connect()
	return frappe


def _schema_snapshot(frappe, doctypes: list[str]) -> dict:
	queue = deque(doctypes)
	seen = set()
	schemas = {}
	while queue:
		doctype = queue.popleft()
		if not doctype or doctype in seen:
			continue
		seen.add(doctype)
		meta = frappe.get_meta(doctype)
		fields = []
		for field in meta.fields:
			fields.append(
				{
					"fieldname": field.fieldname,
					"fieldtype": field.fieldtype,
					"options": field.options,
					"default": field.default,
					"reqd": int(field.reqd or 0),
				}
			)
			if field.fieldtype in TABLE_FIELD_TYPES and field.options:
				queue.append(field.options)
		schemas[doctype] = {
			"issingle": int(meta.issingle or 0),
			"istable": int(meta.istable or 0),
			"fields": fields,
		}
	return schemas


def _quote_identifier(value: str) -> str:
	return "`" + str(value).replace("`", "``") + "`"


def _field_stats(frappe, requests: list[dict]) -> list[dict]:
	results = []
	for request in requests:
		doctype = str(request["doctype"])
		fieldname = str(request["fieldname"])
		fieldtype = str(request.get("fieldtype") or "")
		where = str(request.get("where") or "").strip()
		if not frappe.db.has_column(doctype, fieldname):
			results.append({**request, "physical_column": False})
			continue

		column = _quote_identifier(fieldname)
		table = _quote_identifier("tab" + doctype)
		meaningful = f"{column} is not null and cast({column} as char) != ''"
		if fieldtype in {"Check", "Int", "Float", "Currency", "Percent"}:
			meaningful += f" and {column} != 0"
		where_clause = f" where {where}" if where else ""
		row = frappe.db.sql(
			f"""
			select count(*) as row_count,
				sum(case when {column} is not null then 1 else 0 end) as stored_count,
				sum(case when {meaningful} then 1 else 0 end) as meaningful_count
			from {table}{where_clause}
			""",
			as_dict=True,
		)[0]
		sample_where = f"({meaningful})"
		if where:
			sample_where = f"({where}) and {sample_where}"
		samples = frappe.db.sql(
			f"select distinct cast({column} as char) from {table} "
			f"where {sample_where} limit 5",
			pluck=True,
		)
		results.append(
			{
				**request,
				"physical_column": True,
				"row_count": int(row.row_count or 0),
				"stored_count": int(row.stored_count or 0),
				"meaningful_count": int(row.meaningful_count or 0),
				"samples": samples,
			}
		)
	return results


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--bench", type=Path, required=True)
	parser.add_argument("--site", required=True)
	parser.add_argument("--doctypes-json")
	parser.add_argument("--field-requests-json")
	args = parser.parse_args()
	frappe = _connect(args.bench.resolve(), args.site)
	try:
		if args.field_requests_json:
			payload = _field_stats(frappe, json.loads(args.field_requests_json))
		else:
			doctypes = json.loads(args.doctypes_json or "[]")
			payload = _schema_snapshot(frappe, doctypes)
		print(json.dumps(payload, sort_keys=True, default=str))
	finally:
		frappe.destroy()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
