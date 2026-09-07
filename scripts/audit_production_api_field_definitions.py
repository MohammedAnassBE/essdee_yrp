#!/usr/bin/env python3
"""Audit source field definitions and physical columns missing from YRP apps.

This diagnostic is deliberately broader than the migration planner.  Besides
the live Production API DocType metadata, it inspects physical MariaDB columns
and stored child ``(parenttype, parentfield)`` contexts so deleted/stale source
metadata cannot hide historical data.  It is read-only and never emits secret
values.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from audit_production_api_source_values import (
	LAYOUT_FIELD_TYPES,
	NUMERIC_FIELD_TYPES,
	Route,
	_connect,
	_field_route,
	_quote,
	_schema_fields,
)


STANDARD_COLUMNS = {
	"name",
	"creation",
	"modified",
	"modified_by",
	"owner",
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
}


def _owner_index(bench: Path) -> dict[str, str]:
	result: dict[str, str] = {}
	for app in ("yrp", "essdee_yrp"):
		for path in (bench / "apps" / app).glob("**/doctype/*/*.json"):
			try:
				payload = json.loads(path.read_text(encoding="utf-8"))
			except (OSError, ValueError):
				continue
			if payload.get("doctype") == "DocType" and payload.get("name"):
				result[str(payload["name"])] = app
	return result


def _target_doctype_owner(target_doctype: str, owners: Mapping[str, str]) -> str:
	if target_doctype in owners:
		return owners[target_doctype]
	if target_doctype == "SMS Settings":
		return "frappe (custom field/archive via essdee_yrp)"
	return "unmapped target owner"


def _audited_field_stats(value_audit: Mapping[str, Any]):
	stats: dict[tuple[str, str], dict[str, int]] = defaultdict(
		lambda: {
			"values_seen": 0,
			"nonblank_values": 0,
			"material_values": 0,
		}
	)
	for row in value_audit.get("field_results") or []:
		if row.get("source_fieldtype") == "System":
			continue
		key = (str(row["source_doctype"]), str(row["source_field"]))
		stats[key]["values_seen"] += int(row.get("source_values_seen") or 0)
		stats[key]["nonblank_values"] += int(row.get("source_nonblank_values") or 0)
		stats[key]["material_values"] += int(row.get("source_material_values") or 0)
	return stats


def _auth_count(source_db, doctype: str, fieldname: str) -> int:
	with source_db.cursor() as cursor:
		cursor.execute(
			"SELECT COUNT(*) AS count FROM __Auth "
			"WHERE doctype=%s AND fieldname=%s "
			"AND password IS NOT NULL AND password!=''",
			(doctype, fieldname),
		)
		return int(cursor.fetchone()["count"] or 0)


def _child_context_count(
	source_db,
	child_doctype: str,
	parenttype: str,
	parentfield: str,
) -> tuple[int, int, int]:
	with source_db.cursor() as cursor:
		cursor.execute(
			f"SELECT name, parent FROM {_quote('tab' + child_doctype)} "
			"WHERE parenttype=%s AND parentfield=%s",
			(parenttype, parentfield),
		)
		rows = list(cursor.fetchall())
		cursor.execute(
			"SELECT 1 FROM information_schema.tables "
			"WHERE table_schema=DATABASE() AND table_name=%s",
			("tab" + parenttype,),
		)
		parent_has_table = bool(cursor.fetchone())
	if not parent_has_table:
		return len(rows), len(rows), 0
	parent_names = sorted({str(row.get("parent") or "") for row in rows})
	existing: set[str] = set()
	for offset in range(0, len(parent_names), 1000):
		batch = parent_names[offset : offset + 1000]
		if not batch:
			continue
		placeholders = ",".join(["%s"] * len(batch))
		with source_db.cursor() as cursor:
			cursor.execute(
				f"SELECT name FROM {_quote('tab' + parenttype)} "
				f"WHERE name IN ({placeholders})",
				batch,
			)
			existing.update(str(row["name"]) for row in cursor.fetchall())
	attached = sum(str(row.get("parent") or "") in existing for row in rows)
	return len(rows), attached, len(rows) - attached


def _missing_live_metadata_fields(
	plan,
	source_db,
	stats,
	owners,
	value_audit: Mapping[str, Any],
) -> list[dict[str, Any]]:
	rows = []
	for source_doctype, spec in sorted(plan.specs.items()):
		target_fields = _schema_fields(spec.target_schema)
		for fieldname, source_field in _schema_fields(spec.source_schema).items():
			fieldtype = str(source_field.get("fieldtype") or "")
			if fieldtype in LAYOUT_FIELD_TYPES:
				continue
			target_names, disposition, reason = _field_route(
				plan,
				Route(source_doctype, spec.target),
				fieldname,
				source_field,
			)
			present = [name for name in target_names if name in target_fields]
			if target_names and len(present) == len(target_names):
				continue
			field_stats = dict(stats[(source_doctype, fieldname)])
			child_rows = attached_rows = orphan_rows = 0
			if fieldtype in {"Table", "Table MultiSelect"} and source_field.get("options"):
				child_rows, attached_rows, orphan_rows = _child_context_count(
					source_db,
					str(source_field["options"]),
					source_doctype,
					fieldname,
				)
			auth_rows = _auth_count(source_db, source_doctype, fieldname) if fieldtype == "Password" else 0
			has_information = bool(
				field_stats["material_values"] or child_rows or auth_rows
			)
			note = ""
			if source_doctype == "Essdee Debit" and fieldname == "against":
				classification = "Semantically retained"
				severity = "retained"
				action = "No duplicate field required; keep explicit discriminator verification."
			elif has_information:
				classification = "Target field absent with source data"
				severity = "blocker"
				action = "Create a safe target/archive field or obtain an explicit retirement decision."
			else:
				classification = "Target field absent; source empty/default"
				severity = "empty"
				action = "No current data loss; retain in the inventory before deciding removal."
			rows.append(
				{
					"source_layer": "live DocType metadata",
					"source_doctype": source_doctype,
					"source_field": fieldname,
					"source_fieldtype": fieldtype,
					"target_doctype": spec.target,
					"target_field": ", ".join(target_names) if target_names else fieldname,
					"target_doctype_owner": _target_doctype_owner(spec.target, owners),
					"target_field_defined": False,
					"values_seen": field_stats["values_seen"],
					"nonblank_values": field_stats["nonblank_values"],
					"material_values": field_stats["material_values"],
					"child_rows": child_rows,
					"attached_child_rows": attached_rows,
					"orphan_child_rows": orphan_rows,
					"auth_rows": auth_rows,
					"disposition": disposition,
					"reason": reason,
					"classification": classification,
					"severity": severity,
					"action": action,
					"note": note,
				}
			)
	return rows


def _direct_field_schema_drift(plan, owners) -> list[dict[str, Any]]:
	"""Flag label/type changes where no explicit field mapping approved them."""
	rows = []
	for source_doctype, spec in sorted(plan.specs.items()):
		target_fields = _schema_fields(spec.target_schema)
		for fieldname, source_field in _schema_fields(spec.source_schema).items():
			if fieldname in spec.ignored_fields or fieldname in spec.field_map:
				continue
			target_field = target_fields.get(fieldname)
			if not target_field:
				continue
			differences = []
			for property_name in ("fieldtype", "label"):
				source_value = str(source_field.get(property_name) or "")
				target_value = str(target_field.get(property_name) or "")
				if source_value != target_value:
					differences.append(
						f"{property_name}: {source_value!r} -> {target_value!r}"
					)
			if not differences:
				continue
			rows.append(
				{
					"source_layer": "live DocType metadata",
					"source_doctype": source_doctype,
					"source_field": fieldname,
					"source_fieldtype": str(source_field.get("fieldtype") or ""),
					"target_doctype": spec.target,
					"target_field": fieldname,
					"target_doctype_owner": _target_doctype_owner(spec.target, owners),
					"target_field_defined": True,
					"values_seen": 0,
					"nonblank_values": 0,
					"material_values": 0,
					"child_rows": 0,
					"attached_child_rows": 0,
					"orphan_child_rows": 0,
					"auth_rows": 0,
					"disposition": "direct field",
					"reason": "; ".join(differences),
					"classification": "Unapproved direct-field schema change",
					"severity": "blocker",
					"action": "Preserve the source fieldtype and label; prefix only the owning DocType.",
					"note": "",
				}
			)
	return rows


def _physical_column_stats(source_db, doctype: str, column: str, data_type: str):
	quoted = _quote(column)
	if data_type in {
		"int",
		"bigint",
		"smallint",
		"tinyint",
		"mediumint",
		"decimal",
		"double",
		"float",
	}:
		nonblank = f"SUM(CASE WHEN {quoted} IS NOT NULL THEN 1 ELSE 0 END)"
		material = f"SUM(CASE WHEN COALESCE({quoted},0)<>0 THEN 1 ELSE 0 END)"
	else:
		nonblank = (
			f"SUM(CASE WHEN {quoted} IS NOT NULL "
			f"AND CAST({quoted} AS CHAR)<>'' THEN 1 ELSE 0 END)"
		)
		material = nonblank
	with source_db.cursor() as cursor:
		cursor.execute(
			f"SELECT COUNT(*) AS total_rows, {nonblank} AS nonblank_rows, "
			f"{material} AS material_rows FROM {_quote('tab' + doctype)}"
		)
		row = cursor.fetchone()
	return {
		"rows": int(row["total_rows"] or 0),
		"nonblank_values": int(row["nonblank_rows"] or 0),
		"material_values": int(row["material_rows"] or 0),
	}


def _fg_parent_lot_reconciliation(source_db) -> dict[str, int]:
	with source_db.cursor() as cursor:
		cursor.execute(
			"""
			SELECT COUNT(*) AS parents,
			       SUM(CASE WHEN child_count>0 AND mismatch_count=0 THEN 1 ELSE 0 END)
			         AS all_children_same,
			       SUM(child_count) AS child_rows
			FROM (
			  SELECT parent.name, COUNT(item.name) AS child_count,
			         SUM(CASE WHEN COALESCE(item.lot,'')<>COALESCE(parent.lot,'')
			                  THEN 1 ELSE 0 END) AS mismatch_count
			  FROM `tabFG Stock Entry` parent
			  LEFT JOIN `tabFG Stock Entry Detail` item
			    ON item.parent=parent.name
			   AND item.parenttype='FG Stock Entry'
			   AND item.parentfield='items'
			  WHERE COALESCE(parent.lot,'')!=''
			  GROUP BY parent.name
			) grouped
			"""
		)
		row = cursor.fetchone()
	return {
		"parents": int(row["parents"] or 0),
		"all_children_same": int(row["all_children_same"] or 0),
		"child_rows": int(row["child_rows"] or 0),
	}


def _physical_schema_drift(plan, source_db, owners) -> list[dict[str, Any]]:
	rows = []
	fg_lot = _fg_parent_lot_reconciliation(source_db)
	for source_doctype, spec in sorted(plan.specs.items()):
		if spec.source_schema.get("issingle"):
			continue
		source_fields = set(_schema_fields(spec.source_schema))
		target_fields = _schema_fields(spec.target_schema)
		with source_db.cursor() as cursor:
			cursor.execute(
				"SELECT column_name, data_type FROM information_schema.columns "
				"WHERE table_schema=DATABASE() AND table_name=%s",
				("tab" + source_doctype,),
			)
			columns = list(cursor.fetchall())
		for column in columns:
			fieldname = str(column["column_name"])
			if fieldname in source_fields or fieldname in STANDARD_COLUMNS:
				continue
			data_type = str(column["data_type"])
			field_stats = _physical_column_stats(
				source_db, source_doctype, fieldname, data_type
			)
			target_defined = fieldname in target_fields
			if target_defined:
				classification = "Target defines field; source metadata is stale"
				severity = "retained" if not field_stats["material_values"] else "review"
				action = "Ensure the migration bridge includes this physical column if it becomes populated."
			elif field_stats["material_values"]:
				classification = "Physical source data; target field absent"
				severity = "blocker"
				action = "Create/map/archive this field; current metadata-driven migration cannot see it."
			else:
				classification = "Physical legacy column empty/default"
				severity = "empty"
				action = "No current informative values; document before schema cleanup."
			note = ""
			if source_doctype == "FG Stock Entry" and fieldname == "lot":
				classification = "Parent field absent; value duplicated in every child"
				severity = "retained"
				action = "No raw parent field exists, but retain the child-lot reconciliation gate."
				note = (
					f"{fg_lot['all_children_same']} of {fg_lot['parents']} populated parents "
					f"match all {fg_lot['child_rows']} FG Stock Entry Detail.lot rows."
				)
			rows.append(
				{
					"source_layer": "physical SQL column absent from live metadata",
					"source_doctype": source_doctype,
					"source_field": fieldname,
					"source_fieldtype": data_type,
					"target_doctype": spec.target,
					"target_field": fieldname,
					"target_doctype_owner": _target_doctype_owner(spec.target, owners),
					"target_field_defined": target_defined,
					"values_seen": field_stats["rows"],
					"nonblank_values": field_stats["nonblank_values"],
					"material_values": field_stats["material_values"],
					"child_rows": 0,
					"attached_child_rows": 0,
					"orphan_child_rows": 0,
					"auth_rows": 0,
					"disposition": "not in source DocType metadata",
					"reason": "Physical historical column is invisible to the source bridge schema.",
					"classification": classification,
					"severity": severity,
					"action": action,
					"note": note,
				}
			)
	return rows


def _legacy_child_contexts(
	plan,
	source_db,
	value_audit: Mapping[str, Any],
	owners,
) -> list[dict[str, Any]]:
	rows = []
	for inferred in value_audit.get("inferred_child_routes") or []:
		source_context = str(inferred["source_context"])
		parenttype, parentfield = source_context.split(".", 1)
		source_doctype = str(inferred["source_doctype"])
		target_parenttype, target_parentfield = str(inferred["target_context"]).split(
			".", 1
		)
		count, attached, orphan = _child_context_count(
			source_db, source_doctype, parenttype, parentfield
		)
		target_parent_spec = plan.specs.get(parenttype)
		target_fields = (
			_schema_fields(target_parent_spec.target_schema)
			if target_parent_spec
			else {}
		)
		# Historical inferred routes are inputs, not proof that the new bridge
		# still omits this context. Re-evaluate against the current schema plan.
		source_fields = _schema_fields(target_parent_spec.source_schema) if target_parent_spec else {}
		if parentfield in source_fields and target_parentfield in target_fields:
			continue
		rows.append(
			{
				"source_layer": "stored child context absent from live parent metadata",
				"source_doctype": parenttype,
				"source_field": parentfield,
				"source_fieldtype": f"Table → {source_doctype}",
				"target_doctype": target_parenttype,
				"target_field": target_parentfield,
				"target_doctype_owner": _target_doctype_owner(target_parenttype, owners),
				"target_field_defined": target_parentfield in target_fields,
				"values_seen": count,
				"nonblank_values": count,
				"material_values": count,
				"child_rows": count,
				"attached_child_rows": attached,
				"orphan_child_rows": orphan,
				"auth_rows": 0,
				"disposition": "not declared by source parent metadata",
				"reason": str(inferred.get("reason") or ""),
				"classification": "Stored child table field absent in target",
				"severity": "blocker",
				"action": "Create/map/archive the parent Table field and migrate its physical child rows.",
			}
		)
	return rows


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
	target_absent = [row for row in rows if not row["target_field_defined"]]
	carrying_data = [
		row
		for row in target_absent
		if row["material_values"] or row["child_rows"] or row["auth_rows"]
	]
	return {
		"inventory_rows": len(rows),
		"target_absent_definitions": len(target_absent),
		"target_absent_with_source_data": len(carrying_data),
		"unresolved_blockers": sum(row["severity"] == "blocker" for row in rows),
		"semantically_retained_or_recoverable": sum(
			row["severity"] == "retained" and row in carrying_data for row in rows
		),
		"target_absent_empty_or_default": sum(
			row["severity"] == "empty" and not row["target_field_defined"]
			for row in rows
		),
		"by_target_doctype_owner": {
			app: {
				"inventory": sum(row["target_doctype_owner"] == app for row in rows),
				"blockers": sum(
					row["target_doctype_owner"] == app
					and row["severity"] == "blocker"
					for row in rows
				),
			}
			for app in sorted({row["target_doctype_owner"] for row in rows})
		},
	}


def _safe_json(value: Any) -> str:
	return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
		"</", "<\\/"
	)


def _render(payload: Mapping[str, Any]) -> str:
	summary = payload["summary"]
	rows = payload["rows"]
	body = "".join(
		"<tr>" + "".join(
			f"<td>{html.escape(str(row.get(key, '')))}</td>"
			for key in (
				"source_doctype", "source_field", "target_doctype", "target_field",
				"target_doctype_owner", "material_values", "classification", "action",
			)
		) + "</tr>" for row in rows
	)
	return f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Production API field-definition audit</title>
<style>body{{font:15px/1.5 system-ui;margin:2rem;color:#182230;background:#f7f8fa}}h1{{font-size:1.6rem}}
.summary{{display:flex;flex-wrap:wrap;gap:1rem}}.card{{padding:1rem;background:white;border:1px solid #ccc;border-radius:8px}}
strong{{display:block;font-size:1.5rem}}.table{{overflow:auto;background:white}}table{{border-collapse:collapse;width:100%}}
td,th{{padding:.7rem;text-align:left;border:1px solid #ddd;vertical-align:top}}th{{background:#e9edf4}}
input{{margin:1rem 0;padding:.7rem;width:min(90%,36rem)}}p{{max-width:80rem}}</style>
<h1>Production API → YRP / SD YRP: field-definition audit</h1>
<p>Generated {html.escape(payload['generated_on'])}. Source: {html.escape(payload['source']['site'])}.
Target: {html.escape(payload['target']['site'])}.</p>
<div class="summary">
<div class="card"><strong>{summary['unresolved_blockers']}</strong>unresolved definition gaps with data</div>
<div class="card"><strong>{summary['target_absent_definitions']}</strong>absent target definitions</div>
<div class="card"><strong>{summary['target_absent_empty_or_default']}</strong>empty/default-only source definitions</div>
<div class="card"><strong>{summary['semantically_retained_or_recoverable']}</strong>semantically retained definitions</div>
</div>
<p>This read-only inventory checks current schema mappings, physical source columns and historical child contexts.
A mapped definition does <em>not</em> prove that its values have been loaded: use the separate full value reconciliation,
credential checks and attachment-byte verification for migration acceptance. Empty/default-only retired fields remain listed;
renamed fields with a target mapping are not missing definitions.</p>
<input id="search" aria-label="Filter fields" placeholder="Filter by DocType, field, app or classification">
<div class="table"><table><thead><tr><th>Source DocType</th><th>Source field</th><th>Target DocType</th>
<th>Target field</th><th>Target DocType owner</th><th>Material values</th><th>Finding</th><th>Disposition / action</th>
</tr></thead><tbody>{body}</tbody></table></div>
<script>document.getElementById('search').addEventListener('input',e=>{{
const q=e.target.value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.textContent.toLowerCase().includes(q));}});</script>
</html>"""


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--site")
	parser.add_argument(
		"--bench", type=Path, default=Path(__file__).resolve().parents[3]
	)
	parser.add_argument("--value-audit", type=Path)
	parser.add_argument("--json-output", type=Path, required=True)
	parser.add_argument("--html-output", type=Path, required=True)
	parser.add_argument(
		"--render-existing",
		action="store_true",
		help="Render HTML from the existing JSON audit without reconnecting to either site.",
	)
	args = parser.parse_args()
	bench = args.bench.resolve()
	json_output_path = args.json_output.resolve()
	html_output_path = args.html_output.resolve()
	if args.render_existing:
		payload = json.loads(json_output_path.read_text(encoding="utf-8"))
		html_output_path.write_text(_render(payload), encoding="utf-8")
		print(json.dumps(payload["summary"], indent=2))
		return 0
	if not args.site or not args.value_audit:
		parser.error("--site and --value-audit are required unless --render-existing is used")
	value_audit_path = args.value_audit.resolve()
	sys.path.insert(0, str(bench / "apps"))
	os.chdir(bench / "sites")

	import frappe

	frappe.init(site=args.site, sites_path=str(bench / "sites"))
	frappe.connect()
	try:
		from essdee_yrp.migration.config import get_migration_settings
		from essdee_yrp.migration.live import F15SourceBridge, build_live_schema_analysis

		settings = get_migration_settings()
		plan, _ = build_live_schema_analysis(settings, F15SourceBridge(settings))
		if not plan.ready:
			raise RuntimeError("Migration plan is not ready: " + "; ".join(plan.issues))
		value_audit = json.loads(value_audit_path.read_text(encoding="utf-8"))
		owners = _owner_index(bench)
		source_db = _connect(settings.source_bench, settings.source_site)
		try:
			stats = _audited_field_stats(value_audit)
			metadata_rows = _missing_live_metadata_fields(
				plan, source_db, stats, owners, value_audit
			)
			direct_schema_rows = _direct_field_schema_drift(plan, owners)
			physical_rows = _physical_schema_drift(plan, source_db, owners)
			context_rows = _legacy_child_contexts(
				plan, source_db, value_audit, owners
			)
		finally:
			source_db.close()
		rows = sorted(
			metadata_rows + direct_schema_rows + physical_rows + context_rows,
			key=lambda row: (
				{"blocker": 0, "review": 1, "retained": 2, "empty": 3}.get(
					row["severity"], 9
				),
				row["target_doctype_owner"],
				row["source_doctype"],
				row["source_field"],
			),
		)
		payload = {
			"generated_on": dt.datetime.now().astimezone().isoformat(),
			"read_only": True,
			"source": {
				"bench": str(settings.source_bench),
				"site": settings.source_site,
				"app": settings.source_app,
			},
			"target": {
				"bench": str(bench),
				"site": args.site,
				"apps": ["yrp", "essdee_yrp"],
			},
			"summary": _summary(rows),
			"rows": rows,
		}
		json_output_path.write_text(
			json.dumps(payload, indent=2, default=str), encoding="utf-8"
		)
		html_output_path.write_text(_render(payload), encoding="utf-8")
		print(json.dumps(payload["summary"], indent=2))
	finally:
		frappe.destroy()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
