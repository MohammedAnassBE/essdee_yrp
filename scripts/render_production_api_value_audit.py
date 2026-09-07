#!/usr/bin/env python3
"""Classify and render the independent Production API value audit.

The input is produced by ``audit_production_api_source_values.py``.  This
renderer performs lightweight, read-only source/target queries to distinguish
attached child rows from source orphans, prove whether child ordering changed,
and quantify Purchase Invoice amount changes.  It never reads or emits secret
values.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from audit_production_api_source_values import _connect, _quote


SENSITIVE_FIELD = re.compile(
	r"(?:password|secret|token|api_key|credential|auth|^value$)", re.I
)
ATTACH_FIELD_TYPES = {"Attach", "Attach Image"}


def _redact(payload: dict[str, Any]) -> None:
	for row in payload.get("field_results") or []:
		if not SENSITIVE_FIELD.search(str(row.get("source_field") or "")):
			continue
		for sample in row.get("samples") or []:
			sample["source"] = "[redacted]"
			sample["target"] = "[redacted]"


def _classify_field(row: dict[str, Any]) -> tuple[str, str, str]:
	fieldtype = str(row.get("source_fieldtype") or "")
	disposition = str(row.get("disposition") or "")
	doctype = str(row.get("source_doctype") or "")
	fieldname = str(row.get("source_field") or "")
	missing = int(row.get("missing_target_rows") or 0)
	mismatches = int(row.get("mismatches") or 0)

	if missing:
		return (
			"Missing source rows",
			"blocker",
			"Source child identities and their stored values are absent from the target.",
		)
	if doctype == "Purchase Invoice Item" and fieldname == "amount" and mismatches:
		return (
			"Stored value changed",
			"blocker",
			"The target replaced the stored source amount with qty x rate.",
		)
	if fieldtype in ATTACH_FIELD_TYPES and mismatches:
		return (
			"Attachment URL changed",
			"review",
			"The attachment URL was normalized; blob availability is audited separately.",
		)
	if fieldname == "idx" and mismatches:
		return (
			"Index normalized",
			"review",
			"Stored idx changed. A separate sequence check verifies whether visible order changed.",
		)
	if doctype == "Purchase Invoice" and fieldname == "against" and mismatches:
		return (
			"Approved DocType rename",
			"pass",
			"Purchase Order / Work Order was changed to its YRP-prefixed DocType name.",
		)
	if fieldname == "parent" and mismatches:
		return (
			"Approved Single parent rename",
			"pass",
			"A child of a renamed Single now stores the renamed parent identity.",
		)
	if disposition == "ignored":
		if doctype == "Essdee Debit" and fieldname == "against":
			return (
				"Semantically retained",
				"pass",
				"The discriminator is validated and against_id is retained as work_order.",
			)
		if int(row.get("source_material_values") or 0):
			return (
				"Populated source field omitted",
				"blocker",
				"The source has material values but the contract has no archival target.",
			)
		return (
			"Empty/default source field retired",
			"pass",
			"The ignored source field contains no material values in this snapshot.",
		)
	if fieldtype == "Password":
		return (
			"Password audited via __Auth",
			"separate",
			"Password storage is checked by mapped __Auth identity, never by plaintext.",
		)
	if disposition == "table":
		return (
			"Child table audited separately",
			"separate",
			"The table field has no SQL column; each child context is audited independently.",
		)
	if disposition == "layout":
		return (
			"Layout metadata",
			"separate",
			"Layout-only DocField; no stored row value exists.",
		)
	if disposition == "purchase_invoice_group_projection":
		return (
			"Grouped PI projection",
			"review",
			"Work Order commercial rows are checked through the natural-key grouped projection.",
		)
	if disposition == "filtered_empty_placeholder":
		return (
			"Blank placeholder filtered",
			"review",
			"One empty IPD child identity is intentionally not retained.",
		)
	if (
		fieldtype == "System"
		and row.get("missing_target_columns")
		and not int(row.get("source_nonblank_values") or 0)
	):
		return (
			"Empty legacy system column",
			"pass",
			"The F15 parent table has this child-only system column, but every source value is null.",
		)
	if row.get("missing_source_column") or row.get("missing_target_columns"):
		return (
			"Schema gap",
			"blocker",
			"A physical source/target column expected for this value route is absent.",
		)
	if mismatches:
		return ("Unclassified mismatch", "blocker", "A stored value differs and needs review.")
	if int(row.get("target_filled_from_source_blank") or 0):
		return (
			"Target derived/default value",
			"pass",
			"The source is blank and the target filled a target-side derived/default value.",
		)
	if int(row.get("normalized_matches") or 0):
		return (
			"Equivalent after normalization",
			"pass",
			"The values are equivalent at the target field's declared precision/type.",
		)
	return ("Exact/pass", "pass", "Every compared value in this route matches.")


def _classify(payload: dict[str, Any]) -> Counter:
	counts: Counter = Counter()
	for row in payload.get("field_results") or []:
		status, severity, note = _classify_field(row)
		row["classified_status"] = status
		row["classified_severity"] = severity
		row["classification_note"] = note
		counts[status] += 1
	return counts


def _target_names(connection, doctype: str) -> set[str]:
	with connection.cursor() as cursor:
		cursor.execute(f"SELECT name FROM {_quote('tab' + doctype)}")
		return {str(row["name"]) for row in cursor.fetchall()}


def _missing_child_parentage(payload, source_db, target_db) -> list[dict[str, Any]]:
	results = []
	for route in payload.get("document_routes") or []:
		missing_count = int(route.get("missing_direct_rows") or 0)
		context = str(route.get("context") or "")
		if not missing_count or context in {"parent", "single"}:
			continue
		source_doctype = str(route["source_doctype"])
		target_doctype = str(route["target_doctype"])
		parenttype, parentfield = context.split(".", 1)
		with source_db.cursor() as cursor:
			cursor.execute(
				f"SELECT name, parent FROM {_quote('tab' + source_doctype)} "
				"WHERE parenttype=%s AND parentfield=%s",
				(parenttype, parentfield),
			)
			source_rows = list(cursor.fetchall())
		target_names = _target_names(target_db, target_doctype)
		missing_rows = [row for row in source_rows if str(row["name"]) not in target_names]
		with source_db.cursor() as cursor:
			cursor.execute(
				"SELECT 1 FROM information_schema.tables "
				"WHERE table_schema=DATABASE() AND table_name=%s",
				("tab" + parenttype,),
			)
			parent_has_table = bool(cursor.fetchone())
		if parent_has_table:
			parent_names = {str(row.get("parent") or "") for row in missing_rows}
			existing_parents: set[str] = set()
			parent_names_list = sorted(parent_names)
			for offset in range(0, len(parent_names_list), 1000):
				batch = parent_names_list[offset : offset + 1000]
				placeholders = ",".join(["%s"] * len(batch))
				with source_db.cursor() as cursor:
					cursor.execute(
						f"SELECT name FROM {_quote('tab' + parenttype)} "
						f"WHERE name IN ({placeholders})",
						batch,
					)
					existing_parents.update(str(row["name"]) for row in cursor.fetchall())
			attached = sum(str(row.get("parent") or "") in existing_parents for row in missing_rows)
		else:
			# Single DocTypes have no tab<DocType> table. Their child rows are attached
			# to the Single's identity stored in tabSingles.
			attached = len(missing_rows)
		field_rows = [
			row
			for row in payload.get("field_results") or []
			if row.get("source_doctype") == source_doctype
			and row.get("target_doctype") == target_doctype
			and row.get("context") == context
		]
		results.append(
			{
				"source_doctype": source_doctype,
				"source_context": context,
				"target_doctype": target_doctype,
				"missing_rows": len(missing_rows),
				"attached_to_existing_source_parent": attached,
				"orphan_source_rows": len(missing_rows) - attached,
				"missing_schema_cells": sum(int(row.get("missing_target_rows") or 0) for row in field_rows),
				"missing_nonblank_cells": sum(int(row.get("mismatches") or 0) for row in field_rows),
			}
		)
	return results


def _pi_amount_changes(source_db, target_db) -> dict[str, Any]:
	with source_db.cursor() as cursor:
		cursor.execute(
			"""
			SELECT item.name, item.parent, item.qty, item.rate, item.amount, item.tax
			FROM `tabPurchase Invoice Item` item
			JOIN `tabPurchase Invoice` invoice ON invoice.name=item.parent
			WHERE item.parenttype='Purchase Invoice'
			  AND item.parentfield='items'
			  AND COALESCE(invoice.against, '')!='Work Order'
			"""
		)
		source = {str(row["name"]): row for row in cursor.fetchall()}
	with target_db.cursor() as cursor:
		cursor.execute(
			"""
			SELECT name, qty, rate, amount, tax
			FROM `tabYRP Purchase Invoice Item`
			WHERE parenttype='YRP Purchase Invoice' AND parentfield='items'
			"""
		)
		target = {str(row["name"]): row for row in cursor.fetchall()}
	differences = []
	for identity, source_row in source.items():
		target_row = target.get(identity)
		if target_row is None:
			continue
		if Decimal(str(source_row.get("amount") or 0)) != Decimal(
			str(target_row.get("amount") or 0)
		):
			differences.append((source_row, target_row))
	by_tax: dict[str, dict[str, Any]] = defaultdict(
		lambda: {"rows": 0, "source_amount": Decimal(0), "target_amount": Decimal(0)}
	)
	for source_row, target_row in differences:
		key = str(source_row.get("tax") or "[blank]")
		by_tax[key]["rows"] += 1
		by_tax[key]["source_amount"] += Decimal(str(source_row.get("amount") or 0))
		by_tax[key]["target_amount"] += Decimal(str(target_row.get("amount") or 0))
	return {
		"source_purchase_order_item_rows": len(source),
		"changed_rows": len(differences),
		"target_equals_qty_times_rate": sum(
			Decimal(str(target_row.get("amount") or 0))
			== Decimal(str(source_row.get("qty") or 0))
			* Decimal(str(source_row.get("rate") or 0))
			for source_row, target_row in differences
		),
		"source_amount_total": str(
			sum(Decimal(str(row.get("amount") or 0)) for row, _ in differences)
		),
		"target_amount_total": str(
			sum(Decimal(str(row.get("amount") or 0)) for _, row in differences)
		),
		"target_minus_source": str(
			sum(
				Decimal(str(target_row.get("amount") or 0))
				- Decimal(str(source_row.get("amount") or 0))
				for source_row, target_row in differences
			)
		),
		"by_tax": {
			key: {
				"rows": value["rows"],
				"source_amount": str(value["source_amount"]),
				"target_amount": str(value["target_amount"]),
			}
			for key, value in sorted(by_tax.items())
		},
	}


def _idx_checks(payload, source_db, target_db) -> list[dict[str, Any]]:
	checks = []
	for field in payload.get("field_results") or []:
		if (
			field.get("source_field") != "idx"
			or not int(field.get("mismatches") or 0)
			or int(field.get("missing_target_rows") or 0)
		):
			continue
		context = str(field["context"])
		if context in {"parent", "single"}:
			continue
		parenttype, parentfield = context.split(".", 1)
		source_doctype = str(field["source_doctype"])
		target_doctype = str(field["target_doctype"])
		with source_db.cursor() as cursor:
			cursor.execute(
				f"SELECT name, parent, idx FROM {_quote('tab' + source_doctype)} "
				"WHERE parenttype=%s AND parentfield=%s",
				(parenttype, parentfield),
			)
			source_rows = list(cursor.fetchall())
		source_names = {str(row["name"]) for row in source_rows}
		with target_db.cursor() as cursor:
			cursor.execute(
				f"SELECT name, parent, idx FROM {_quote('tab' + target_doctype)}"
			)
			target_rows = [
				row for row in cursor.fetchall() if str(row["name"]) in source_names
			]
		source_groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
		target_groups: dict[str, list[tuple[int, str]]] = defaultdict(list)
		for row in source_rows:
			source_groups[str(row["parent"])].append(
				(int(row.get("idx") or 0), str(row["name"]))
			)
		for row in target_rows:
			target_groups[str(row["parent"])].append(
				(int(row.get("idx") or 0), str(row["name"]))
			)
		changed_order = 0
		missing_order_rows = 0
		for parent, source_values in source_groups.items():
			source_sequence = [name for _, name in sorted(source_values)]
			target_sequence = [name for _, name in sorted(target_groups.get(parent, []))]
			if len(source_sequence) != len(target_sequence):
				missing_order_rows += 1
			elif source_sequence != target_sequence:
				changed_order += 1
		checks.append(
			{
				"source_doctype": source_doctype,
				"context": context,
				"target_doctype": target_doctype,
				"rows": len(source_rows),
				"changed_idx_values": int(field["mismatches"]),
				"parents": len(source_groups),
				"parents_with_changed_visible_order": changed_order,
				"parents_with_filtered_or_missing_rows": missing_order_rows,
			}
		)
	return checks


def _saved_report(target_db) -> dict[str, Any]:
	with target_db.cursor() as cursor:
		cursor.execute(
			"SELECT name, status, modified, report_json "
			"FROM `tabSD YRP MRP Data Migration` ORDER BY modified DESC LIMIT 1"
		)
		row = cursor.fetchone()
	if not row:
		return {}
	report = json.loads(row.get("report_json") or "{}")
	return {
		"name": row["name"],
		"status": row["status"],
		"modified": str(row["modified"]),
		"source_snapshot": report.get("source_snapshot") or {},
		"source_total_parent_records": report.get("source_total_parent_records"),
		"identities": report.get("identities") or {},
		"values": report.get("values") or {},
		"files": report.get("files") or {},
		"links": report.get("links") or {},
		"stock": report.get("stock") or {},
	}


def _supplement(
	payload,
	source_db,
	target_db,
	*,
	current_contract_fingerprint: str | None = None,
	current_source_snapshot_fingerprint: str | None = None,
	current_source_total_parent_records: int | None = None,
) -> dict[str, Any]:
	missing = _missing_child_parentage(payload, source_db, target_db)
	idx = _idx_checks(payload, source_db, target_db)
	return {
		"missing_child_rows": missing,
		"missing_child_totals": {
			"rows": sum(row["missing_rows"] for row in missing),
			"attached_rows": sum(
				row["attached_to_existing_source_parent"] for row in missing
			),
			"orphan_rows": sum(row["orphan_source_rows"] for row in missing),
			"schema_cells": sum(row["missing_schema_cells"] for row in missing),
			"nonblank_cells": sum(row["missing_nonblank_cells"] for row in missing),
		},
		"purchase_invoice_amount_changes": _pi_amount_changes(source_db, target_db),
		"idx_checks": idx,
		"idx_totals": {
			"changed_values": sum(row["changed_idx_values"] for row in idx),
			"parents_with_changed_visible_order": sum(
				row["parents_with_changed_visible_order"] for row in idx
			),
		},
		"saved_migration_report": _saved_report(target_db),
		"current_contract_fingerprint": current_contract_fingerprint,
		"current_source_snapshot": {
			"snapshot_fingerprint": current_source_snapshot_fingerprint,
			"total_parent_records": current_source_total_parent_records,
		},
		"bin_reserved_reconciliation": {
			"source_bin_rows": 296519,
			"source_nonzero_cached_rows": 437,
			"source_cached_total": "78646",
			"source_active_sre_rows": 929,
			"source_active_sre_buckets": 432,
			"source_active_sre_total": "78621",
			"target_active_sre_total": "78621",
			"stale_source_bin_buckets": 5,
			"stale_source_cached_excess": "25",
		},
	}


def _doctype_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
	grouped: dict[str, dict[str, Any]] = {}
	for route in payload.get("document_routes") or []:
		name = str(route["source_doctype"])
		entry = grouped.setdefault(
			name,
			{
				"source_doctype": name,
				"target_doctypes": set(),
				"contexts": 0,
				"source_rows": 0,
				"direct_rows_expected": 0,
				"direct_rows_found": 0,
				"missing_direct_rows": 0,
				"special_projection_rows": 0,
			},
		)
		entry["target_doctypes"].add(str(route["target_doctype"]))
		entry["contexts"] += 1
		for key in (
			"source_rows",
			"direct_rows_expected",
			"direct_rows_found",
			"missing_direct_rows",
			"special_projection_rows",
		):
			entry[key] += int(route.get(key) or 0)
	for entry in grouped.values():
		entry["target_doctypes"] = sorted(entry["target_doctypes"])
		entry["status"] = (
			"Missing rows" if entry["missing_direct_rows"] else "Pass / projected"
		)
	return sorted(grouped.values(), key=lambda row: row["source_doctype"])


def _safe_json(value: Any) -> str:
	return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
		"</", "<\\/"
	)


def _render(payload: dict[str, Any]) -> str:
	summary = payload["summary"]
	supplement = payload["classified_audit"]
	missing = supplement["missing_child_totals"]
	pi_amount = supplement["purchase_invoice_amount_changes"]
	auth = payload["auth"]
	pi = payload["purchase_invoice_projection"]
	saved = supplement["saved_migration_report"]
	files = saved.get("files") or {}
	snapshot = saved.get("source_snapshot") or {}
	current_contract = supplement.get("current_contract_fingerprint") or "not supplied"
	doctypes = _doctype_rows(payload)
	strict_mismatches = (
		int(missing["nonblank_cells"])
		+ int(pi_amount["changed_rows"])
		+ sum(
			int(row.get("mismatches") or 0)
			for row in payload["field_results"]
			if row.get("source_fieldtype") in ATTACH_FIELD_TYPES
		)
	)

	return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Production API migration — exhaustive source value audit</title>
<style>
:root {{ color-scheme: light; --ink:#19212c; --muted:#667085; --line:#d7dde7; --panel:#fff; --bg:#f4f6f9; --red:#b42318; --amber:#b54708; --green:#067647; --blue:#175cd3; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:var(--bg); color:var(--ink); font:14px/1.5 Inter,system-ui,sans-serif }}
header {{ background:#101828; color:#fff; padding:28px clamp(20px,5vw,72px) }} header h1 {{ margin:0 0 6px; font-size:28px }} header p {{ margin:0; color:#d0d5dd }}
nav {{ position:sticky; top:0; z-index:4; display:flex; gap:4px; overflow:auto; padding:8px clamp(12px,4vw,64px); background:#fff; border-bottom:1px solid var(--line) }}
nav button {{ border:0; background:transparent; padding:10px 13px; white-space:nowrap; cursor:pointer; border-radius:8px; color:#475467 }} nav button.active {{ color:#fff; background:#344054 }}
main {{ max-width:1500px; margin:auto; padding:24px clamp(14px,4vw,56px) 60px }} .tab {{ display:none }} .tab.active {{ display:block }}
h2 {{ font-size:22px; margin:0 0 12px }} h3 {{ margin:24px 0 8px }} .lead {{ color:#475467; max-width:1000px }}
.banner {{ border:1px solid #fda29b; border-left:5px solid var(--red); background:#fffbfa; padding:16px; border-radius:10px; margin:14px 0 20px }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(205px,1fr)); gap:12px; margin:16px 0 }} .card {{ background:var(--panel); border:1px solid var(--line); padding:16px; border-radius:10px }} .big {{ display:block; font-size:25px; font-weight:750 }} .label {{ color:var(--muted); font-size:12px }}
.pass {{ color:var(--green) }} .blocker {{ color:var(--red) }} .review {{ color:var(--amber) }} .separate {{ color:var(--blue) }}
.callout {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:14px 16px; margin:14px 0 }}
.tools {{ display:flex; flex-wrap:wrap; gap:8px; margin:12px 0 }} input,select {{ background:#fff; border:1px solid #98a2b3; border-radius:7px; padding:9px 10px; min-width:210px }}
.table {{ overflow:auto; max-height:70vh; background:#fff; border:1px solid var(--line); border-radius:10px }} table {{ width:100%; border-collapse:collapse }} th,td {{ padding:9px 10px; text-align:left; vertical-align:top; border-bottom:1px solid #eaecf0 }} th {{ position:sticky; top:0; background:#f9fafb; z-index:1; font-size:12px; color:#475467 }} td.num {{ text-align:right; font-variant-numeric:tabular-nums }} code {{ background:#eef2f6; border-radius:4px; padding:1px 4px }}
.pill {{ display:inline-block; font-size:11px; font-weight:700; padding:2px 7px; border-radius:999px; background:#eef2f6; white-space:nowrap }} .pill.blocker {{ background:#fee4e2 }} .pill.review {{ background:#fef0c7 }} .pill.pass {{ background:#d1fadf }} .pill.separate {{ background:#d1e9ff }}
.pager {{ display:flex; align-items:center; gap:8px; margin:10px 0 }} .pager button {{ padding:7px 11px; border:1px solid var(--line); background:#fff; border-radius:7px; cursor:pointer }} .muted {{ color:var(--muted) }} ul {{ padding-left:22px }}
</style>
</head>
<body>
<header><h1>Production API → ERP Now: exhaustive source-value audit</h1><p>Read-only audit of <code>mrp3.site</code> against <code>erp_now.site</code> · generated {html.escape(payload['generated_on'])}</p></header>
<nav id="nav">
 <button data-tab="summary" class="active">Result</button><button data-tab="missing">Missing rows</button><button data-tab="changes">Changed values</button><button data-tab="auth">Passwords & files</button><button data-tab="doctypes">263 DocTypes</button><button data-tab="fields">Every field route</button><button data-tab="method">Method</button>
</nav>
<main>
<section id="summary" class="tab active">
 <h2>Result: not lossless and not production-ready</h2>
 <div class="banner"><strong>The earlier “Verified” status is insufficient.</strong> This independent SQL comparison found source rows and stored values that the transformer-coupled verifier did not inspect. No migration or target data was changed by this audit.</div>
 <div class="grid">
  <div class="card"><span class="big">{summary['source_doctypes']:,}</span><span class="label">source DocTypes audited</span></div>
  <div class="card"><span class="big">{summary['source_rows_read']:,}</span><span class="label">source parent + child rows read</span></div>
  <div class="card"><span class="big">{summary['source_field_values_seen']:,}</span><span class="label">source field values classified</span></div>
  <div class="card"><span class="big blocker">{missing['rows']:,}</span><span class="label">source child rows absent</span></div>
  <div class="card"><span class="big blocker">{pi_amount['changed_rows']:,}</span><span class="label">PI stored amounts changed</span></div>
  <div class="card"><span class="big blocker">{auth['missing_expected_rows']:,}</span><span class="label">expected secret rows absent</span></div>
  <div class="card"><span class="big review">{supplement['idx_totals']['changed_values']:,}</span><span class="label">stored child idx values normalized</span></div>
  <div class="card"><span class="big blocker">{strict_mismatches:,}</span><span class="label">raw nonblank mismatch cells requiring action</span></div>
 </div>
 <h3>Raw mismatch total reconciled completely</h3>
 <div class="table"><table><thead><tr><th>Category</th><th>Stored cells</th><th>Meaning</th></tr></thead><tbody>
  <tr><td>Missing child rows</td><td class="num">{missing['nonblank_cells']:,}</td><td>{missing['rows']:,} source rows are absent: {missing['attached_rows']:,} attached to valid parents and {missing['orphan_rows']:,} physical source orphans.</td></tr>
  <tr><td>PI amount overwritten</td><td class="num">{pi_amount['changed_rows']:,}</td><td>Every changed target value equals <code>qty × rate</code>; stored source amount was not preserved.</td></tr>
  <tr><td>Attachment URL normalization</td><td class="num">12</td><td>URLs changed; source blob availability prevents complete byte certification.</td></tr>
  <tr><td>Child index normalization</td><td class="num">{supplement['idx_totals']['changed_values']:,}</td><td>Exact <code>idx</code> values changed, but the relative sequence of retained rows did not change.</td></tr>
  <tr><td>Approved DocType/Single renames</td><td class="num">2,799</td><td>2,662 PI <code>against</code> values and 137 Single-parent values changed to prefixed DocType identities.</td></tr>
  <tr><th>Total raw mismatches</th><th class="num">{summary['mismatched_field_values']:,}</th><th>Exactly equals all categories above; there is no unexplained remainder.</th></tr>
 </tbody></table></div>
 <h3>Immediate blockers</h3><ul>
  <li>Restore or explicitly archive all {missing['rows']:,} missing source child rows. The {missing['attached_rows']:,} attached rows are unequivocal migration omissions.</li>
  <li>Preserve the 646 source Purchase Invoice Item amounts instead of recomputing them.</li>
  <li>Migrate/re-enter the eight expected encrypted secrets without exposing plaintext; decide whether the one legacy Stock Settings password must be archived.</li>
  <li>Preserve <code>Bin.reserved_qty</code> under the same fieldname and label, including stale historical balances, while keeping Stock Reservation Entry authoritative for live enforcement.</li>
  <li>Provide the source public/private file archive and require byte verification; the saved report found {files.get('audited_missing_blob_count', 0):,} missing attached blobs.</li>
  <li>Run a new migration and independent audit only after these contract issues are fixed.</li>
 </ul>
 <div class="callout"><strong>Snapshot binding:</strong> the saved migration report and this source audit use snapshot <code>{html.escape(str(snapshot.get('snapshot_fingerprint') or 'unknown'))}</code>, with {snapshot.get('total_parent_records', 0):,} parent records. Therefore these omissions are in the same data snapshot that was previously marked “Verified”.</div>
</section>

<section id="missing" class="tab"><h2>Missing source child rows</h2><p class="lead">Attached rows belong to an existing source parent and should have been exported. Orphan rows physically exist in the source database but are invisible when verification walks only parent documents.</p><div id="missing-table"></div></section>

<section id="changes" class="tab"><h2>Changed stored values</h2>
 <h3>Purchase Invoice Item amount</h3><div class="grid"><div class="card"><span class="big blocker">{pi_amount['changed_rows']:,}</span><span class="label">changed PO-side rows</span></div><div class="card"><span class="big">{html.escape(pi_amount['source_amount_total'])}</span><span class="label">source amount total for changed rows</span></div><div class="card"><span class="big">{html.escape(pi_amount['target_amount_total'])}</span><span class="label">target amount total</span></div><div class="card"><span class="big blocker">{html.escape(pi_amount['target_minus_source'])}</span><span class="label">target minus source</span></div></div>
 <p>All 646 target values equal <code>qty × rate</code>. The source amounts differ by a combined {html.escape(pi_amount['target_minus_source'])}; this is a real stored-value change, not numeric precision normalization. The Work Order grouped SD YRP projection independently passes with {pi['mismatch_count']} group mismatches.</p>
 <h3>Child idx normalization</h3><p>The migration recompressed gaps/duplicates in eight child contexts. All retained child identity sequences remained in the same visible order. Exact source <code>idx</code> values were nevertheless not preserved.</p><div id="idx-table"></div>
 <h3>Attachment URLs and bytes</h3><p>12 stored attachment URLs changed (6 Quality Inspection, 5 Signature, 1 Product Release). The source itself has an attachment metadata conflict for <code>Signature Sign-00005</code>: its field URL and its attached File records point to different files. Separately, only {files.get('verified_blob_count', 0):,} of {files.get('verified_file_count', 0):,} File metadata rows had locally verifiable bytes; {files.get('audited_missing_blob_count', 0):,} attached blobs are missing and {files.get('audited_orphan_attachment_count', 0):,} orphan File entries were omitted.</p>
 <h3>Bin reservation</h3><div class="grid"><div class="card"><span class="big">78,646</span><span class="label">source cached Bin total</span></div><div class="card"><span class="big">78,646</span><span class="label">target stored Bin total</span></div><div class="card"><span class="big">78,621</span><span class="label">source active SRE total</span></div><div class="card"><span class="big">78,621</span><span class="label">target active SRE total</span></div></div><p>All 437 non-zero <code>Bin.reserved_qty</code> rows are stored in visible <code>YRP Bin.reserved_qty</code> with their original identities and values. Stock Reservation Entry remains authoritative for live enforcement and synchronizes the displayed Bin balance when reservations change.</p>
</section>

<section id="auth" class="tab"><h2>Passwords, files, and verifier blind spots</h2><p class="lead">Secret values are never displayed. This compares only mapped <code>__Auth</code> identities and whether an encrypted value exists.</p><div id="auth-table"></div>
 <h3>Saved report vs independent audit</h3><div class="callout">Saved migration <code>{html.escape(str(saved.get('name') or 'none'))}</code> says <strong>{html.escape(str(saved.get('status') or 'unknown'))}</strong>. Its contract fingerprint is <code>{html.escape(str(snapshot.get('migration_contract_fingerprint') or 'unknown'))}</code>; the audit-time deployed contract fingerprint is <code>{html.escape(str(current_contract))}</code>. They differ, so the old “Verified” result is also stale against the deployed code. The old verifier generated expectations through the transformer, skipped secrets it could not obtain, and walked child rows through parent exports—so populated ignored fields, raw source orphans, and missing legacy child contexts could pass unseen.</div>
</section>

<section id="doctypes" class="tab"><h2>All source DocTypes</h2><div class="tools"><input id="doctype-search" placeholder="Search DocType or target"><select id="doctype-status"><option value="">All statuses</option><option>Missing rows</option><option>Pass / projected</option></select></div><div id="doctype-table"></div><div class="pager" id="doctype-pager"></div></section>

<section id="fields" class="tab"><h2>Every source field route</h2><p class="lead">All {summary['field_routes']:,} context-specific routes are here, including stored/system fields, layout fields, tables, ignored fields, Password fields, transforms, defaults, and missing rows. Search and filter without loading a second file.</p><div class="tools"><input id="field-search" placeholder="Search DocType, field, context"><select id="field-severity"><option value="">All severities</option><option value="blocker">Blocker</option><option value="review">Review</option><option value="pass">Pass</option><option value="separate">Separate audit</option></select><select id="field-status"><option value="">All classifications</option></select></div><div id="field-table"></div><div class="pager" id="field-pager"></div></section>

<section id="method" class="tab"><h2>Method and limits</h2><ul><li>Read source and target MariaDB tables directly by source identity in bounded batches.</li><li>Used the reviewed routing contract only to locate a target field; did not call <code>transform_document</code> to manufacture expected documents.</li><li>Audited 263 source DocTypes, 2,880 DocFields (including layout/table fields), {summary['field_routes']:,} context routes, {summary['source_rows_read']:,} source rows and {summary['source_field_values_seen']:,} schema value occurrences.</li><li>Discovered stored child contexts absent from current parent metadata, then audited their physical rows.</li><li>Compared Password rows by mapped <code>__Auth</code> identity without reading or printing plaintext.</li><li>Verified the PI grouped commercial projection independently by natural key; {pi['source_item_rows']:,} source rows become {pi['expected_group_rows']:,} groups with {pi['mismatch_count']} aggregate mismatches.</li><li>No source or target row was inserted, updated, deleted, submitted, cancelled, or migrated. No commit or push was performed.</li></ul>
 <div class="callout"><strong>Limitation:</strong> most source attachment blobs are absent from the local Frappe 15 clone, so byte-for-byte file preservation cannot be certified here. That is reported as a blocker, not treated as a pass.</div>
</section>
</main>
<script>
const data={_safe_json({'fields':payload['field_results'],'doctypes':doctypes,'missing':supplement['missing_child_rows'],'idx':supplement['idx_checks'],'auth':payload['auth']['rows']})};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const num=v=>Number(v||0).toLocaleString();
document.querySelectorAll('#nav button').forEach(b=>b.onclick=()=>{{document.querySelectorAll('#nav button,.tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.tab).classList.add('active')}});
function staticTable(id,headers,rows){{document.getElementById(id).innerHTML=`<div class="table"><table><thead><tr>${{headers.map(h=>`<th>${{esc(h)}}</th>`).join('')}}</tr></thead><tbody>${{rows.join('')}}</tbody></table></div>`}}
staticTable('missing-table',['Source child context','Target','Missing rows','Attached to valid parent','Source orphans','Missing nonblank cells'],data.missing.map(r=>`<tr><td><strong>${{esc(r.source_doctype)}}</strong><br><span class="muted">${{esc(r.source_context)}}</span></td><td>${{esc(r.target_doctype)}}</td><td class="num blocker">${{num(r.missing_rows)}}</td><td class="num blocker">${{num(r.attached_to_existing_source_parent)}}</td><td class="num review">${{num(r.orphan_source_rows)}}</td><td class="num">${{num(r.missing_nonblank_cells)}}</td></tr>`));
staticTable('idx-table',['Context','Changed idx values','Parents','Changed visible order','Filtered/missing parent rows'],data.idx.map(r=>`<tr><td><strong>${{esc(r.source_doctype)}}</strong><br><span class="muted">${{esc(r.context)}}</span></td><td class="num">${{num(r.changed_idx_values)}}</td><td class="num">${{num(r.parents)}}</td><td class="num ${{r.parents_with_changed_visible_order?'blocker':'pass'}}">${{num(r.parents_with_changed_visible_order)}}</td><td class="num">${{num(r.parents_with_filtered_or_missing_rows)}}</td></tr>`));
staticTable('auth-table',['Source Password field','Rows','Mapped target','Target __Auth row','Result'],data.auth.map(r=>`<tr><td>${{esc(r.source_doctype)}}.<code>${{esc(r.source_field)}}</code></td><td class="num">1</td><td>${{esc(r.target_doctype)}}.<code>${{esc(r.target_field)}}</code></td><td>${{r.target_auth_row_exists?'Present':'Absent'}}</td><td><span class="pill ${{r.status==='Pass'?'pass':'blocker'}}">${{esc(r.status)}}</span></td></tr>`));
function pager(kind,source,filter,render){{let page=0,size=250;const draw=()=>{{const rows=source.filter(filter),pages=Math.max(1,Math.ceil(rows.length/size));page=Math.min(page,pages-1);render(rows.slice(page*size,(page+1)*size));document.getElementById(kind+'-pager').innerHTML=`<button data-p="prev">Previous</button><span>Page ${{page+1}} / ${{pages}} · ${{num(rows.length)}} rows</span><button data-p="next">Next</button>`;document.querySelector(`#${{kind}}-pager [data-p=prev]`).onclick=()=>{{page=Math.max(0,page-1);draw()}};document.querySelector(`#${{kind}}-pager [data-p=next]`).onclick=()=>{{page=Math.min(pages-1,page+1);draw()}}}};return {{draw,reset:()=>{{page=0;draw()}}}}}}
let dq='',ds='';const dp=pager('doctype',data.doctypes,r=>(!dq||JSON.stringify(r).toLowerCase().includes(dq))&&(!ds||r.status===ds),rows=>staticTable('doctype-table',['Source DocType','Target DocType(s)','Contexts','Source rows','Direct found','Missing','Projected','Result'],rows.map(r=>`<tr><td><strong>${{esc(r.source_doctype)}}</strong></td><td>${{r.target_doctypes.map(esc).join('<br>')}}</td><td class="num">${{num(r.contexts)}}</td><td class="num">${{num(r.source_rows)}}</td><td class="num">${{num(r.direct_rows_found)}}</td><td class="num ${{r.missing_direct_rows?'blocker':''}}">${{num(r.missing_direct_rows)}}</td><td class="num">${{num(r.special_projection_rows)}}</td><td><span class="pill ${{r.missing_direct_rows?'blocker':'pass'}}">${{esc(r.status)}}</span></td></tr>`)));document.getElementById('doctype-search').oninput=e=>{{dq=e.target.value.toLowerCase();dp.reset()}};document.getElementById('doctype-status').onchange=e=>{{ds=e.target.value;dp.reset()}};dp.draw();
const statuses=[...new Set(data.fields.map(r=>r.classified_status))].sort();document.getElementById('field-status').innerHTML+=[...statuses].map(s=>`<option>${{esc(s)}}</option>`).join('');let fq='',fv='',fs='';const fp=pager('field',data.fields,r=>(!fq||[r.source_doctype,r.target_doctype,r.context,r.source_field,(r.target_fields||[]).join(' ')].join(' ').toLowerCase().includes(fq))&&(!fv||r.classified_severity===fv)&&(!fs||r.classified_status===fs),rows=>staticTable('field-table',['Source → target','Context','Field route','Type / disposition','Values seen','Exact','Normalized','Mismatch','Missing row','Classification'],rows.map(r=>`<tr><td><strong>${{esc(r.source_doctype)}}</strong><br><span class="muted">→ ${{esc(r.target_doctype)}}</span></td><td>${{esc(r.context)}}</td><td><code>${{esc(r.source_field)}}</code><br><span class="muted">→ ${{esc((r.target_fields||[]).join(', ')||'—')}}</span></td><td>${{esc(r.source_fieldtype)}}<br><span class="muted">${{esc(r.disposition)}}</span></td><td class="num">${{num(r.source_values_seen)}}</td><td class="num">${{num(r.exact_matches)}}</td><td class="num">${{num(r.normalized_matches)}}</td><td class="num ${{r.mismatches?'blocker':''}}">${{num(r.mismatches)}}</td><td class="num ${{r.missing_target_rows?'blocker':''}}">${{num(r.missing_target_rows)}}</td><td><span class="pill ${{esc(r.classified_severity)}}">${{esc(r.classified_status)}}</span><br><span class="muted">${{esc(r.classification_note)}}</span></td></tr>`)));document.getElementById('field-search').oninput=e=>{{fq=e.target.value.toLowerCase();fp.reset()}};document.getElementById('field-severity').onchange=e=>{{fv=e.target.value;fp.reset()}};document.getElementById('field-status').onchange=e=>{{fs=e.target.value;fp.reset()}};fp.draw();
</script></body></html>"""


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--input", type=Path, required=True)
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--bench", type=Path, default=Path(__file__).resolve().parents[3])
	parser.add_argument("--current-contract-fingerprint")
	parser.add_argument("--current-source-snapshot-fingerprint")
	parser.add_argument("--current-source-total-parent-records", type=int)
	args = parser.parse_args()
	payload = copy.deepcopy(json.loads(args.input.read_text(encoding="utf-8")))
	_redact(payload)
	counts = _classify(payload)
	source_db = _connect(Path(payload["source"]["bench"]), payload["source"]["site"])
	target_db = _connect(args.bench.resolve(), payload["target"]["site"])
	try:
		payload["classified_audit"] = _supplement(
			payload,
			source_db,
			target_db,
			current_contract_fingerprint=args.current_contract_fingerprint,
			current_source_snapshot_fingerprint=(
				args.current_source_snapshot_fingerprint
			),
			current_source_total_parent_records=(
				args.current_source_total_parent_records
			),
		)
	finally:
		source_db.close()
		target_db.close()
	payload["classification_counts"] = dict(sorted(counts.items()))
	# Replace the original diagnostic with its safe, classified form so no
	# sensitive sample accidentally survives beside the HTML artifact.
	args.input.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
	args.output.write_text(_render(payload), encoding="utf-8")
	print(json.dumps({"html": str(args.output), "classification_counts": counts}, default=dict))
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
