#!/usr/bin/env python3
"""Independently audit every stored Production API value against the target.

This is a read-only diagnostic.  It uses the reviewed DocType/field routing
contract only to locate a target value; it does not call ``transform_document``
to manufacture expected documents.  Source and target rows are read directly
from their databases and compared by source identity in bounded batches.

The generated JSON is intentionally exhaustive: every source field has a
disposition, including empty fields, ignored fields, table fields, Password
fields, renamed fields, and fields handled by custom transformations.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import decimal
import json
import hashlib
import os
import re
import sys
import time
from hmac import compare_digest
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import pymysql
from cryptography.fernet import Fernet, InvalidToken
from pymysql.cursors import DictCursor, SSDictCursor


TABLE_FIELD_TYPES = {"Table", "Table MultiSelect"}
LAYOUT_FIELD_TYPES = {
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Heading",
	"Fold",
}
NUMERIC_FIELD_TYPES = {"Check", "Int", "Float", "Currency", "Percent"}
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
SENSITIVE_FIELD = re.compile(
	r"(?:password|secret|token|api_key|credential|auth|^value$)", re.I
)
SAMPLE_LIMIT = 5


@dataclass(frozen=True)
class Route:
	source_doctype: str
	target_doctype: str
	source_parenttype: str | None = None
	source_parentfield: str | None = None
	target_parenttype: str | None = None
	target_parentfield: str | None = None

	@property
	def label(self) -> str:
		if not self.source_parenttype:
			return "parent"
		return f"{self.source_parenttype}.{self.source_parentfield}"


@dataclass
class FieldAudit:
	source_doctype: str
	target_doctype: str
	context: str
	source_field: str
	target_fields: list[str]
	source_fieldtype: str
	disposition: str
	reason: str = ""
	source_rows: int = 0
	source_values_seen: int = 0
	source_nonblank_values: int = 0
	source_material_values: int = 0
	source_blank_values: int = 0
	compared_values: int = 0
	exact_matches: int = 0
	normalized_matches: int = 0
	target_filled_from_source_blank: int = 0
	verified_default_fills: int = 0
	default_fill_rule: str = ""
	mismatches: int = 0
	missing_target_rows: int = 0
	missing_source_column: bool = False
	missing_target_columns: list[str] = field(default_factory=list)
	samples: list[dict[str, Any]] = field(default_factory=list)

	@property
	def status(self) -> str:
		if self.missing_source_column:
			return "Schema Gap"
		if self.missing_target_columns and not (
			self.source_fieldtype == "System" and not self.source_nonblank_values
		):
			return "Schema Gap"
		if self.missing_target_rows or self.mismatches:
			return "Mismatch"
		if self.normalized_matches or self.target_filled_from_source_blank != self.verified_default_fills:
			return "Review Required"
		if self.disposition == "ignored" and self.source_material_values:
			return "Ignored With Material Data"
		if self.disposition in {
			"password",
			"table",
			"layout",
			"purchase_invoice_group_projection",
			"filtered_empty_placeholder",
		}:
			return "Separate Audit"
		return "Verified default fill (not exact copy)" if self.verified_default_fills else "Pass"

	def payload(self) -> dict[str, Any]:
		value = asdict(self)
		value["status"] = self.status
		return value


def _load_site_config(bench: Path, site: str) -> dict[str, Any]:
	common_path = bench / "sites" / "common_site_config.json"
	site_path = bench / "sites" / site / "site_config.json"
	common = json.loads(common_path.read_text()) if common_path.is_file() else {}
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
		autocommit=False,
	)


def _quote(value: str) -> str:
	return "`" + value.replace("`", "``") + "`"


def _schema_fields(schema: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
	return {
		str(row["fieldname"]): row
		for row in schema.get("fields") or []
		if row.get("fieldname")
	}


def _columns(connection, doctype: str) -> dict[str, dict[str, Any]]:
	with connection.cursor() as cursor:
		cursor.execute(
			"""
			SELECT column_name, data_type, numeric_scale
			FROM information_schema.columns
			WHERE table_schema=DATABASE() AND table_name=%s
			""",
			("tab" + doctype,),
		)
		return {str(row["column_name"]): row for row in cursor.fetchall()}


def _row_count(connection, route: Route, *, target: bool) -> int:
	doctype = route.target_doctype if target else route.source_doctype
	parenttype = route.target_parenttype if target else route.source_parenttype
	parentfield = route.target_parentfield if target else route.source_parentfield
	query = f"SELECT COUNT(*) AS count FROM {_quote('tab' + doctype)}"
	params: list[Any] = []
	if parenttype:
		query += " WHERE parenttype=%s AND parentfield=%s"
		params.extend((parenttype, parentfield))
	with connection.cursor() as cursor:
		cursor.execute(query, params)
		return int(cursor.fetchone()["count"] or 0)


def _iter_source_batches(
	connection,
	route: Route,
	columns: Iterable[str],
	batch_size: int,
) -> Iterable[list[dict[str, Any]]]:
	selected = ", ".join(_quote(column) for column in columns)
	query = f"SELECT {selected} FROM {_quote('tab' + route.source_doctype)}"
	params: list[Any] = []
	if route.source_parenttype:
		query += " WHERE parenttype=%s AND parentfield=%s"
		params.extend((route.source_parenttype, route.source_parentfield))
	query += " ORDER BY name"
	with connection.cursor(SSDictCursor) as cursor:
		cursor.execute(query, params)
		while True:
			rows = cursor.fetchmany(batch_size)
			if not rows:
				break
			yield list(rows)


def _target_rows(connection, doctype: str, names: list[str]) -> dict[str, dict[str, Any]]:
	if not names:
		return {}
	placeholders = ",".join(["%s"] * len(names))
	query = (
		f"SELECT * FROM {_quote('tab' + doctype)} "
		f"WHERE name IN ({placeholders})"
	)
	with connection.cursor() as cursor:
		cursor.execute(query, names)
		return {str(row["name"]): row for row in cursor.fetchall()}


def _single_values(connection, doctype: str) -> dict[str, Any]:
	with connection.cursor() as cursor:
		cursor.execute(
			"SELECT field, value FROM tabSingles WHERE doctype=%s",
			(doctype,),
		)
		return {str(row["field"]): row["value"] for row in cursor.fetchall()}


def _plain(value: Any) -> Any:
	if isinstance(value, decimal.Decimal):
		return format(value, "f")
	if isinstance(value, (dt.datetime, dt.date, dt.time)):
		return str(value)
	if isinstance(value, bytes):
		return value.decode(errors="replace")
	return value


def _sample_value(fieldname: str, value: Any) -> Any:
	if SENSITIVE_FIELD.search(fieldname):
		return "[redacted]"
	value = _plain(value)
	if isinstance(value, str) and len(value) > 180:
		return value[:177] + "..."
	return value


def _is_blank(value: Any) -> bool:
	return value is None or value == ""


def _is_material(value: Any, fieldtype: str) -> bool:
	if _is_blank(value):
		return False
	if fieldtype in NUMERIC_FIELD_TYPES:
		try:
			return decimal.Decimal(str(value)) != 0
		except decimal.InvalidOperation:
			return True
	return True


def _json_value(value: Any) -> Any:
	if isinstance(value, str):
		return json.loads(value)
	return value


def _compare_values(
	expected: Any,
	actual: Any,
	fieldtype: str,
	numeric_scale: int | None,
) -> str:
	"""Return exact, normalized, or mismatch."""
	if expected is None or actual is None:
		return "exact" if expected is None and actual is None else "mismatch"
	if fieldtype in NUMERIC_FIELD_TYPES:
		try:
			left = decimal.Decimal(str(expected or 0))
			right = decimal.Decimal(str(actual or 0))
		except decimal.InvalidOperation:
			return "mismatch"
		if left == right:
			return "exact"
		if numeric_scale is not None:
			quantum = decimal.Decimal(1).scaleb(-numeric_scale)
			if left.quantize(quantum, rounding=decimal.ROUND_HALF_UP) == right:
				return "normalized"
		return "mismatch"
	if fieldtype == "JSON":
		try:
			return "exact" if _json_value(expected) == _json_value(actual) else "mismatch"
		except (TypeError, ValueError, json.JSONDecodeError):
			pass
	return "exact" if str(_plain(expected)) == str(_plain(actual)) else "mismatch"


def _doctype_controllers(schema: Mapping[str, Any]) -> set[str]:
	controllers = {
		str(row.get("options"))
		for row in schema.get("fields") or []
		if row.get("fieldtype") == "Dynamic Link" and row.get("options")
	}
	controllers.update(
		str(row.get("fieldname"))
		for row in schema.get("fields") or []
		if row.get("fieldtype") == "Link"
		and row.get("options") == "DocType"
		and row.get("fieldname")
	)
	return controllers


def _custom_targets(
	source_doctype: str,
	fieldname: str,
	target_fields: set[str],
) -> tuple[list[str], str, str]:
	if source_doctype == "Essdee Debit":
		if fieldname == "against":
			return [], "custom_transform", "Work Order discriminator represented by YRP Debit.work_order"
		if fieldname == "against_id":
			return ["work_order"], "custom_transform", "against_id renamed to work_order"
	if source_doctype == "IPD Process":
		if fieldname == "stage":
			return ["in_stage", "out_stage"], "custom_transform", "stage duplicated into in_stage and out_stage"
	if source_doctype == "Stock Settings":
		mapping = {
			"transit_warehouse": "transit_warehouse",
			"default_received_type": "default_received_type",
			"default_rejected_type": "default_rejected_received_type",
			"default_fg_lot": "default_fg_lot",
			"add_finishing_plan_goods_value": "add_finishing_plan_goods_value",
		}
		if fieldname in mapping:
			return [mapping[fieldname]], "custom_transform", "Stock Settings reviewed mapping"
	if fieldname in target_fields:
		return [fieldname], "direct", "custom transformer common-field copy"
	return [], "unmapped_custom", "custom transformer has no target route"


def _field_route(plan, route: Route, fieldname: str, source_field: Mapping[str, Any]):
	spec = plan.specs[route.source_doctype]
	target_schema = plan.target_schemas[route.target_doctype]
	target_fields = set(_schema_fields(target_schema))
	fieldtype = str(source_field.get("fieldtype") or "")
	if fieldtype in LAYOUT_FIELD_TYPES:
		return [], "layout", "layout-only metadata"
	if fieldtype in TABLE_FIELD_TYPES:
		target_field = spec.field_map.get(fieldname, fieldname)
		return [target_field], "table", "child rows audited in their own route"
	if fieldtype == "Password":
		return [spec.field_map.get(fieldname, fieldname)], "password", "audited through __Auth identity"
	if route.source_doctype == "Essdee Debit" and fieldname == "against" and spec.custom_transformer:
		return _custom_targets(route.source_doctype, fieldname, target_fields)
	if fieldname in spec.ignored_fields:
		return [], "ignored", str(spec.ignored_fields[fieldname])
	if spec.custom_transformer:
		return _custom_targets(route.source_doctype, fieldname, target_fields)
	target_field = spec.field_map.get(fieldname, fieldname)
	disposition = "renamed" if target_field != fieldname else "direct"
	reason = "reviewed field rename" if disposition == "renamed" else "same fieldname"
	if fieldname in spec.value_transformers:
		disposition = "value_transform"
		reason = str(spec.value_transformers[fieldname])
	elif fieldname in _doctype_controllers(spec.source_schema):
		disposition = "doctype_transform"
		reason = "Dynamic Link controller DocType renamed"
	return [target_field], disposition, reason


def _expected_value(plan, route: Route, fieldname: str, value: Any, *, controllers=None) -> Any:
	spec = plan.specs[route.source_doctype]
	if route.source_doctype == "Purchase Invoice" and fieldname == "against":
		return {
			"Work Order": "YRP Work Order",
			"Purchase Order": "YRP Purchase Order",
		}.get(value, value)
	transformer = spec.value_transformers.get(fieldname)
	if transformer == "purchase_order_status":
		return {"Delivered": "Received", "Partially Delivered": "Partially Received"}.get(value, value)
	if transformer == "purchase_order_open_status":
		return "Close" if value == "Closed" else value
	if controllers is None:
		controllers = _doctype_controllers(spec.source_schema)
	if fieldname in controllers and isinstance(value, str):
		target_spec = plan.specs.get(value)
		return target_spec.target if target_spec else value
	return value


def _system_expected(plan, route: Route, fieldname: str, value: Any) -> Any:
	if fieldname == "parent" and route.source_parenttype:
		parent_spec = plan.specs.get(route.source_parenttype)
		if parent_spec and parent_spec.source_schema.get("issingle"):
			return route.target_parenttype
	if fieldname == "parenttype" and route.target_parenttype:
		return route.target_parenttype
	if fieldname == "parentfield" and route.target_parentfield:
		return route.target_parentfield
	return value


class Auditor:
	def __init__(self, plan, source_db, target_db, batch_size: int, *, configured_defaults=None):
		self.plan = plan
		self.source_db = source_db
		self.target_db = target_db
		self.batch_size = batch_size
		self.metrics: dict[tuple[Any, ...], FieldAudit] = {}
		self.documents: list[dict[str, Any]] = []
		self.source_columns: dict[str, dict[str, dict[str, Any]]] = {}
		self.target_columns: dict[str, dict[str, dict[str, Any]]] = {}
		# The reviewed plan is immutable for this audit. Compile only schema
		# routing, never source/target values, once per context instead of for
		# each of the millions of records being independently compared.
		self.row_metrics: dict[Route, list[tuple[str, FieldAudit, bool]]] = {}
		from audit_default_fills import SourceDefaultEvidence

		self.default_evidence = SourceDefaultEvidence(source_db, plan, configured_defaults)
		self.fill_rules = {}
		self.doctype_controllers = {
			name: _doctype_controllers(spec.source_schema) for name, spec in plan.specs.items()
		}
		self.total_source_rows = 0
		self.total_compared_rows = 0
		self.started = time.monotonic()
		self.wo_invoice_names = self._work_order_invoices()

	def _work_order_invoices(self) -> set[str]:
		query = """
			SELECT DISTINCT pi.name
			FROM `tabPurchase Invoice` pi
			LEFT JOIN `tabPI Work Order Billed Detail` wo
			  ON wo.parent=pi.name
			 AND wo.parenttype='Purchase Invoice'
			 AND wo.parentfield='pi_work_order_billed_details'
			WHERE pi.against='Work Order' OR wo.name IS NOT NULL
		"""
		with self.source_db.cursor() as cursor:
			cursor.execute(query)
			return {str(row["name"]) for row in cursor.fetchall()}

	def _source_cols(self, doctype: str):
		if doctype not in self.source_columns:
			self.source_columns[doctype] = _columns(self.source_db, doctype)
		return self.source_columns[doctype]

	def _target_cols(self, doctype: str):
		if doctype not in self.target_columns:
			self.target_columns[doctype] = _columns(self.target_db, doctype)
		return self.target_columns[doctype]

	def _metric(
		self,
		route: Route,
		fieldname: str,
		fieldtype: str,
		target_fields: list[str],
		disposition: str,
		reason: str,
	) -> FieldAudit:
		key = (
			route.source_doctype,
			route.target_doctype,
			route.label,
			fieldname,
			tuple(target_fields),
			disposition,
		)
		if key not in self.metrics:
			self.metrics[key] = FieldAudit(
				source_doctype=route.source_doctype,
				target_doctype=route.target_doctype,
				context=route.label,
				source_field=fieldname,
				target_fields=target_fields,
				source_fieldtype=fieldtype,
				disposition=disposition,
				reason=reason,
			)
		return self.metrics[key]

	def _prepare_metrics(self, route: Route) -> None:
		spec = self.plan.specs[route.source_doctype]
		source_columns = self._source_cols(route.source_doctype)
		target_columns = self._target_cols(route.target_doctype)
		row_metrics = []
		for fieldname, source_field in _schema_fields(spec.source_schema).items():
			targets, disposition, reason = _field_route(
				self.plan, route, fieldname, source_field
			)
			metric = self._metric(
				route,
				fieldname,
				str(source_field.get("fieldtype") or ""),
				targets,
				disposition,
				reason,
			)
			row_metrics.append((fieldname, metric, False))
			if disposition not in {"layout", "table", "password", "ignored"}:
				evidence = self.default_evidence.prepare(route, fieldname, targets)
				self.fill_rules[(route, fieldname)] = evidence
				if evidence:
					metric.default_fill_rule = evidence.rule
			if (
				metric.source_fieldtype not in LAYOUT_FIELD_TYPES | TABLE_FIELD_TYPES
				and metric.source_fieldtype != "Password"
				and fieldname not in source_columns
			):
				metric.missing_source_column = True
			if metric.source_fieldtype not in (
				LAYOUT_FIELD_TYPES | TABLE_FIELD_TYPES | {"Password"}
			):
				metric.missing_target_columns = [
					target for target in targets if target not in target_columns
				]
		for fieldname in SYSTEM_FIELDS:
			if fieldname not in source_columns:
				continue
			metric = self._metric(
				route,
				fieldname,
				"System",
				[fieldname],
				"system",
				"source identity/audit metadata",
			)
			if fieldname not in target_columns:
				metric.missing_target_columns = [fieldname]
			row_metrics.append((fieldname, metric, True))
		self.row_metrics[route] = row_metrics

	def audit_route(self, route: Route) -> None:
		spec = self.plan.specs[route.source_doctype]
		if spec.source_schema.get("issingle"):
			self._audit_single(route)
			return
		self._prepare_metrics(route)
		source_columns = self._source_cols(route.source_doctype)
		query_columns = list(source_columns)
		target_columns = self._target_cols(route.target_doctype)
		source_count = _row_count(self.source_db, route, target=False)
		target_count = _row_count(self.target_db, route, target=True)
		document_result = {
			"source_doctype": route.source_doctype,
			"target_doctype": route.target_doctype,
			"context": route.label,
			"source_rows": source_count,
			"target_rows_in_context": target_count,
			"direct_rows_expected": 0,
			"direct_rows_found": 0,
			"missing_direct_rows": 0,
			"special_projection_rows": 0,
		}
		for batch in _iter_source_batches(
			self.source_db, route, query_columns, self.batch_size
		):
			direct = []
			special = []
			for row in batch:
				if (
					route.source_doctype == "Purchase Invoice Item"
					and str(row.get("parent") or "") in self.wo_invoice_names
				):
					special.append(row)
				elif (
					route.source_doctype == "IPD Process"
					and not row.get("process_name")
				):
					special.append(row)
				else:
					direct.append(row)
			document_result["direct_rows_expected"] += len(direct)
			document_result["special_projection_rows"] += len(special)
			target_by_name = _target_rows(
				self.target_db,
				route.target_doctype,
				[str(row["name"]) for row in direct],
			)
			for row in direct:
				actual = target_by_name.get(str(row["name"]))
				if actual:
					document_result["direct_rows_found"] += 1
				else:
					document_result["missing_direct_rows"] += 1
				self._compare_row(route, row, actual, target_columns)
			for row in special:
				self._record_special_row(route, row)
			self.total_source_rows += len(batch)
			self.total_compared_rows += len(direct)
			if self.total_source_rows and self.total_source_rows % 100000 < len(batch):
				elapsed = max(time.monotonic() - self.started, 0.001)
				print(
					f"AUDIT_PROGRESS rows={self.total_source_rows} "
					f"rate={self.total_source_rows / elapsed:.0f}/s "
					f"doctype={route.source_doctype} "
					f"different_values={sum(m.mismatches for m in self.metrics.values())} "
					f"missing_row_values={sum(m.missing_target_rows for m in self.metrics.values())} "
					f"rounded_values={sum(m.normalized_matches for m in self.metrics.values())} "
					f"filled_blanks={sum(m.target_filled_from_source_blank for m in self.metrics.values())}",
					file=sys.stderr,
					flush=True,
				)
		self.documents.append(document_result)

	def _record_special_row(self, route: Route, source: Mapping[str, Any]) -> None:
		"""Count every value routed through a non-identity projection."""
		spec = self.plan.specs[route.source_doctype]
		if route.source_doctype == "Purchase Invoice Item":
			target_doctype = "SD YRP Essdee Purchase Invoice Item"
			target_map = {
				"item": ["item"],
				"lot": ["lot"],
				"item_group": ["item_group"],
				"expense_head": ["expense_head"],
				"qty": ["qty"],
				"uom": ["uom"],
				"rate": ["rate"],
				"amount": ["amount"],
				"tax": ["tax"],
				"actual_rate": ["source_rate"],
				"actual_qty": [],
			}
			disposition = "purchase_invoice_group_projection"
			reason = "Work Order commercial row audited through the natural-key grouped projection"
		else:
			target_doctype = route.target_doctype
			target_map = {}
			disposition = "filtered_empty_placeholder"
			reason = "blank IPD Process placeholder excluded from operational rows; all original fields checked in the source-process archive"
		for fieldname, source_field in _schema_fields(spec.source_schema).items():
			fieldtype = str(source_field.get("fieldtype") or "")
			metric = self._metric(
				Route(route.source_doctype, target_doctype),
				fieldname,
				fieldtype,
				target_map.get(fieldname, []),
				disposition,
				reason,
			)
			metric.source_rows += 1
			if fieldtype in LAYOUT_FIELD_TYPES | TABLE_FIELD_TYPES or fieldtype == "Password":
				continue
			if fieldname in source:
				self._record_source_value(metric, source[fieldname])
		for fieldname in SYSTEM_FIELDS:
			if fieldname not in source:
				continue
			metric = self._metric(
				Route(route.source_doctype, target_doctype),
				fieldname,
				"System",
				[],
				disposition,
				reason + "; original child identity/system metadata checked independently in the raw source archive",
			)
			metric.source_rows += 1
			self._record_source_value(metric, source[fieldname])

	@staticmethod
	def _record_source_value(metric: FieldAudit, value: Any) -> None:
		metric.source_values_seen += 1
		if _is_blank(value):
			metric.source_blank_values += 1
		else:
			metric.source_nonblank_values += 1
		if _is_material(value, metric.source_fieldtype):
			metric.source_material_values += 1

	def _audit_single(self, route: Route) -> None:
		spec = self.plan.specs[route.source_doctype]
		source = _single_values(self.source_db, route.source_doctype)
		target = _single_values(self.target_db, route.target_doctype)
		target_fields = _schema_fields(self.plan.target_schemas[route.target_doctype])
		for fieldname, source_field in _schema_fields(spec.source_schema).items():
			target_names, disposition, reason = _field_route(
				self.plan, route, fieldname, source_field
			)
			metric = self._metric(
				route,
				fieldname,
				str(source_field.get("fieldtype") or ""),
				target_names,
				disposition,
				reason,
			)
			metric.source_rows = 1
			if metric.source_fieldtype in LAYOUT_FIELD_TYPES | TABLE_FIELD_TYPES:
				continue
			if metric.source_fieldtype == "Password":
				continue
			if fieldname not in source:
				metric.missing_source_column = True
				continue
			self._compare_value(
				metric,
				fieldname,
				source[fieldname],
				target,
				target_fields,
				identity=route.source_doctype,
				route=route,
			)
		self.documents.append(
			{
				"source_doctype": route.source_doctype,
				"target_doctype": route.target_doctype,
				"context": "single",
				"source_rows": 1,
				"target_rows_in_context": 1,
				"direct_rows_expected": 1,
				"direct_rows_found": 1,
				"missing_direct_rows": 0,
				"special_projection_rows": 0,
			}
		)
		self.total_source_rows += 1
		self.total_compared_rows += 1

	def _compare_row(
		self,
		route: Route,
		source: Mapping[str, Any],
		target: Mapping[str, Any] | None,
		target_columns: Mapping[str, Mapping[str, Any]],
	) -> None:
		if route not in self.row_metrics:
			self._prepare_metrics(route)
		for fieldname, metric, is_system in self.row_metrics[route]:
			if is_system and fieldname not in source:
				continue
			metric.source_rows += 1
			if metric.source_fieldtype in LAYOUT_FIELD_TYPES | TABLE_FIELD_TYPES:
				continue
			if metric.source_fieldtype == "Password" or fieldname not in source:
				continue
			value = source[fieldname]
			if is_system:
				value = _system_expected(self.plan, route, fieldname, value)
			self._compare_value(
				metric,
				fieldname,
				value,
				target,
				target_columns,
				identity=str(source.get("name") or ""),
				route=route,
				already_expected=is_system,
			)

	def _compare_value(
		self,
		metric: FieldAudit,
		fieldname: str,
		value: Any,
		target: Mapping[str, Any] | None,
		target_metadata: Mapping[str, Mapping[str, Any]],
		*,
		identity: str,
		route: Route,
		already_expected: bool = False,
	) -> None:
		self._record_source_value(metric, value)
		if metric.disposition in {"ignored", "layout", "table", "password"}:
			return
		if metric.disposition == "custom_transform" and fieldname == "against":
			metric.compared_values += 1
			if value == "Work Order" and target is not None and target.get("work_order"):
				metric.exact_matches += 1
			else:
				metric.mismatches += 1
				self._add_sample(metric, identity, value, "unsupported discriminator")
			return
		if not metric.target_fields:
			if not _is_blank(value):
				metric.mismatches += 1
				self._add_sample(metric, identity, value, None)
			return
		if target is None:
			metric.missing_target_rows += 1
			if not _is_blank(value):
				metric.mismatches += 1
				self._add_sample(metric, identity, value, "[missing target row]")
			return
		expected = value if already_expected else _expected_value(
			self.plan, route, fieldname, value,
			controllers=self.doctype_controllers[route.source_doctype],
		)
		metric.compared_values += 1
		outcomes = []
		actual_values = []
		for target_field in metric.target_fields:
			actual = target.get(target_field)
			actual_values.append(actual)
			metadata = target_metadata.get(target_field) or {}
			fieldtype = metric.source_fieldtype
			if metric.disposition == "custom_transform" and fieldname == "stage":
				fieldtype = "Link"
			outcomes.append(
				_compare_values(
					expected,
					actual,
					fieldtype,
					metadata.get("numeric_scale"),
				)
			)
		if all(outcome == "exact" for outcome in outcomes):
			metric.exact_matches += 1
		elif all(outcome in {"exact", "normalized"} for outcome in outcomes):
			metric.normalized_matches += 1
		elif _is_blank(value) and any(not _is_blank(actual) for actual in actual_values):
			metric.target_filled_from_source_blank += 1
			evidence = self.fill_rules.get((route, fieldname))
			if evidence and evidence.matches(identity, actual_values):
				metric.verified_default_fills += 1
			self._add_sample(metric, identity, value, actual_values)
		else:
			metric.mismatches += 1
			self._add_sample(metric, identity, value, actual_values)

	def _add_sample(self, metric: FieldAudit, identity: str, source: Any, target: Any):
		if len(metric.samples) >= SAMPLE_LIMIT:
			return
		metric.samples.append(
			{
				"name": identity,
				"source": _sample_value(metric.source_field, source),
				"target": _sample_value(metric.source_field, target),
			}
		)


def _child_routes(plan) -> dict[str, list[Route]]:
	routes: dict[str, list[Route]] = defaultdict(list)
	for source_parent, parent_spec in plan.specs.items():
		for fieldname, field in _schema_fields(parent_spec.source_schema).items():
			if field.get("fieldtype") not in TABLE_FIELD_TYPES or not field.get("options"):
				continue
			source_child = str(field["options"])
			if source_child not in plan.specs:
				continue
			target_parentfield = parent_spec.field_map.get(fieldname, fieldname)
			target_child = parent_spec.table_option_map.get(fieldname)
			if not target_child:
				target_parent_fields = _schema_fields(parent_spec.target_schema)
				target_field = target_parent_fields.get(target_parentfield) or {}
				target_child = target_field.get("options") or plan.specs[source_child].target
			route = Route(
				source_doctype=source_child,
				target_doctype=str(target_child),
				source_parenttype=source_parent,
				source_parentfield=fieldname,
				target_parenttype=parent_spec.target,
				target_parentfield=target_parentfield,
			)
			if route not in routes[source_child]:
				routes[source_child].append(route)
	return routes


def _stored_child_routes(plan, source_db, source_doctype: str) -> list[Route]:
	"""Discover legacy child contexts absent from current parent metadata."""
	with source_db.cursor() as cursor:
		cursor.execute(
			f"SELECT parenttype, parentfield, COUNT(*) AS row_count "
			f"FROM {_quote('tab' + source_doctype)} "
			"GROUP BY parenttype, parentfield ORDER BY parenttype, parentfield"
		)
		stored = list(cursor.fetchall())
	routes = []
	for row in stored:
		source_parenttype = str(row.get("parenttype") or "")
		source_parentfield = str(row.get("parentfield") or "")
		parent_spec = plan.specs.get(source_parenttype)
		target_parenttype = parent_spec.target if parent_spec else source_parenttype
		target_parentfield = (
			parent_spec.field_map.get(source_parentfield, source_parentfield)
			if parent_spec
			else source_parentfield
		)
		target_child = plan.specs[source_doctype].target
		if parent_spec:
			target_parent_field = _schema_fields(parent_spec.target_schema).get(
				target_parentfield
			) or {}
			target_child = str(target_parent_field.get("options") or target_child)
		routes.append(
			Route(
				source_doctype=source_doctype,
				target_doctype=target_child,
				source_parenttype=source_parenttype,
				source_parentfield=source_parentfield,
				target_parenttype=target_parenttype,
				target_parentfield=target_parentfield,
			)
		)
	return routes


def _compare_auth_value(source, target, source_key, target_key):
	"""Independent value proof; return only a redacted disposition."""
	if target is None:
		return "Missing", False
	if int(source["encrypted"]) != int(target["encrypted"]):
		return "Encryption flag mismatch", False
	if source["encrypted"]:
		try:
			plain = Fernet(str(source_key).encode()).decrypt(str(source["password"]).encode())
		except (InvalidToken, ValueError, TypeError):
			matches = compare_digest(str(source["password"]).encode(), str(target["password"]).encode())
			return ("Ciphertext preserved; source key unavailable" if matches else "Ciphertext mismatch"), matches
		try:
			actual = Fernet(str(target_key).encode()).decrypt(str(target["password"]).encode())
		except (InvalidToken, ValueError, TypeError):
			return "Target decryption failed", False
		matches = compare_digest(plain, actual)
		return ("Re-encrypted value matches" if matches else "Decrypted value mismatch"), matches
	matches = compare_digest(str(source["password"]).encode(), str(target["password"]).encode())
	return ("Raw value matches" if matches else "Raw value mismatch"), matches


def _credential_record_exists(database, doctype, name, *, is_single=False):
	if is_single:
		return True
	with database.cursor() as cursor:
		cursor.execute(f"SELECT name FROM {_quote('tab' + doctype)} WHERE name=%s", (name,))
		return bool(cursor.fetchone())


def _audit_auth(plan, source_db, target_db, *, source_key=None, target_key=None) -> dict[str, Any]:
	source_doctypes = sorted(plan.specs)
	placeholders = ",".join(["%s"] * len(source_doctypes))
	query = (
		"SELECT doctype, name, fieldname, password, encrypted, "
		"CASE WHEN password IS NULL OR password='' THEN 0 ELSE 1 END AS has_value "
		f"FROM __Auth WHERE doctype IN ({placeholders}) "
		"ORDER BY doctype, name, fieldname"
	)
	with source_db.cursor() as cursor:
		cursor.execute(query, source_doctypes)
		source_rows = list(cursor.fetchall())
	with target_db.cursor() as cursor:
		target_doctypes = sorted({spec.target for spec in plan.specs.values()})
		cursor.execute(
			"SELECT doctype, name, fieldname, password, encrypted FROM __Auth WHERE doctype IN ("
			+ ",".join(["%s"] * len(target_doctypes)) + ")", target_doctypes,
		)
		target_rows = {
			(str(row["doctype"]), str(row["name"]), str(row["fieldname"])): row
			for row in cursor.fetchall()
		}
	results = []
	expected_keys = set()
	for row in source_rows:
		source_doctype = str(row["doctype"])
		fieldname = str(row["fieldname"])
		spec = plan.specs[source_doctype]
		target_field = spec.field_map.get(fieldname, fieldname)
		ignored = fieldname in spec.ignored_fields
		target_name = (
			spec.target if spec.source_schema.get("issingle") else str(row["name"])
		)
		target_identity = (spec.target, target_name, target_field)
		expected_keys.add(target_identity)
		value_status, value_matches = _compare_auth_value(row, target_rows.get(target_identity), source_key, target_key)
		source_exists = _credential_record_exists(source_db, source_doctype, row["name"],
			is_single=bool(spec.source_schema.get("issingle")))
		target_exists = _credential_record_exists(target_db, spec.target, target_name,
			is_single=bool(spec.target_schema.get("issingle")))
		record_identity_matches = source_exists == target_exists
		results.append(
			{
				"source_doctype": source_doctype,
				"source_name": str(row["name"]),
				"source_field": fieldname,
				"source_has_value": bool(row["has_value"]),
				"source_encrypted": bool(row["encrypted"]),
				"target_doctype": spec.target,
				"target_field": target_field,
				"ignored_by_rule": ignored,
				"target_auth_row_exists": target_identity in target_rows,
				"value_status": value_status,
				"value_matches": value_matches,
				"source_record_exists": source_exists,
				"target_record_exists": target_exists,
				"record_identity_matches": record_identity_matches,
				"status": (
					"Ignored With Data"
					if ignored
					else "Record Identity Mismatch"
					if not record_identity_matches
					else "Pass"
					if target_identity in target_rows and value_matches
					else "Value Mismatch"
					if target_identity in target_rows
					else "Missing"
				),
			}
		)
	return {
		"source_auth_rows": len(source_rows),
		"target_rows_found": sum(row["target_auth_row_exists"] for row in results),
		"missing_expected_rows": sum(
			row["status"] == "Missing" for row in results
		),
		"ignored_rows_with_data": sum(
			row["status"] == "Ignored With Data" for row in results
		),
		"value_mismatches": sum(not row["value_matches"] for row in results),
		"record_identity_mismatches": sum(not row["record_identity_matches"] for row in results),
		"source_orphan_rows": sum(not row["source_record_exists"] for row in results),
		"source_key_unavailable_rows": sum(row["value_status"] == "Ciphertext preserved; source key unavailable" for row in results),
		"extra_target_auth_identities": [list(key) for key in sorted(set(target_rows) - expected_keys)],
		"rows": results,
	}


def _decimal_value(value: Any) -> decimal.Decimal:
	return decimal.Decimal(str(value or 0))


def _rate_key(value: Any) -> str:
	return format(_decimal_value(value).quantize(decimal.Decimal("0.000001")), "f")


def _audit_purchase_invoice_projection(source_db, target_db, wo_names: set[str]):
	with source_db.cursor() as cursor:
		cursor.execute(
			"""
			SELECT name, parent, item, lot, item_group, expense_head, qty, uom,
			       rate, amount, tax, actual_rate, actual_qty
			FROM `tabPurchase Invoice Item`
			WHERE parenttype='Purchase Invoice' AND parentfield='items'
			ORDER BY parent, name
			"""
		)
		source_rows = list(cursor.fetchall())
	with target_db.cursor() as cursor:
		cursor.execute(
			"""
			SELECT name, parent, item, lot, item_group, expense_head, qty, uom,
			       source_rate, rate, amount, tax
			FROM `tabSD YRP Essdee Purchase Invoice Item`
			WHERE parenttype='YRP Purchase Invoice' AND parentfield='essdee_items'
			ORDER BY parent, name
			"""
		)
		target_rows = list(cursor.fetchall())
	expected: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
	conflicts = []
	for row in source_rows:
		against_work_order = str(row["parent"]) in wo_names
		source_rate = row.get("actual_rate")
		if not against_work_order and not _decimal_value(source_rate) and _decimal_value(row.get("rate")):
			source_rate = row.get("rate")
		if source_rate in (None, ""):
			source_rate = row.get("rate") or 0
		key = (
			str(row["parent"]),
			str(row.get("item") or ""),
			str(row.get("lot") or ""),
			str(row.get("uom") or ""),
			_rate_key(source_rate),
			str(row.get("tax") or ""),
		)
		group = expected.setdefault(
			key,
			{
				"source_rows": 0,
				"qty": decimal.Decimal(0),
				"amount": decimal.Decimal(0),
				"rate": _decimal_value(row.get("rate")),
				"source_rate": _decimal_value(source_rate),
				"item_group": row.get("item_group"),
				"expense_head": row.get("expense_head"),
			},
		)
		if group["rate"] != _decimal_value(row.get("rate")):
			conflicts.append(f"{row['parent']} conflicting rate for {key[1:]}")
		if group["source_rate"] != _decimal_value(source_rate):
			conflicts.append(f"{row['parent']} conflicting frozen source rate for {key[1:]}")
		if group["expense_head"] and row.get("expense_head") and group["expense_head"] != row.get("expense_head"):
			conflicts.append(f"{row['parent']} conflicting expense head for {key[1:]}")
		group["expense_head"] = group["expense_head"] or row.get("expense_head")
		group["source_rows"] += 1
		group["qty"] += _decimal_value(row.get("qty"))
		group["amount"] += _decimal_value(row.get("qty")) * _decimal_value(row.get("rate"))
	actual: dict[tuple[str, str, str, str, str, str], dict[str, Any]] = {}
	duplicate_actual = []
	for row in target_rows:
		key = (
			str(row["parent"]),
			str(row.get("item") or ""),
			str(row.get("lot") or ""),
			str(row.get("uom") or ""),
			_rate_key(row.get("source_rate")),
			str(row.get("tax") or ""),
		)
		if key in actual:
			duplicate_actual.append(str(key))
		actual[key] = row
	mismatches = []
	for key, source in expected.items():
		target = actual.get(key)
		if not target:
			mismatches.append({"key": list(key), "reason": "missing grouped target row"})
			continue
		checks = {
			"qty": _decimal_value(target.get("qty")) == source["qty"],
			"rate": _decimal_value(target.get("rate")) == source["rate"],
			"source_rate": _decimal_value(target.get("source_rate")) == source["source_rate"],
			"amount": abs(_decimal_value(target.get("amount")) - source["amount"]) <= decimal.Decimal("0.000001"),
			"expense_head": (target.get("expense_head") or None) == (source["expense_head"] or None),
			"item_group": not source["item_group"] or target.get("item_group") == source["item_group"],
		}
		if not all(checks.values()):
			mismatches.append(
				{"key": list(key), "reason": "aggregate mismatch", "checks": checks}
			)
	for key in actual.keys() - expected.keys():
		mismatches.append({"key": list(key), "reason": "unexpected grouped target row"})
	mismatches.extend({"reason": "duplicate grouped target row", "key": key} for key in duplicate_actual)
	mismatches.extend({"reason": "conflicting source group", "detail": conflict} for conflict in conflicts)
	return {
		"source_item_rows": len(source_rows),
		"source_purchase_order_rows": sum(str(row["parent"]) not in wo_names for row in source_rows),
		"source_work_order_rows": sum(str(row["parent"]) in wo_names for row in source_rows),
		"source_actual_qty_nonzero": sum(_decimal_value(row.get("actual_qty")) != 0 for row in source_rows),
		"work_order_actual_qty_nonzero": sum(
			str(row["parent"]) in wo_names and _decimal_value(row.get("actual_qty")) != 0
			for row in source_rows
		),
		"expected_group_rows": len(expected),
		"target_group_rows": len(target_rows),
		"collapsed_source_rows": len(source_rows) - len(expected),
		"missing_groups": sum(key not in actual for key in expected),
		"target_only_groups": sum(key not in expected for key in actual),
		"duplicate_target_groups": duplicate_actual[:20],
		"source_group_conflicts": conflicts[:20],
		"mismatch_count": len(mismatches),
		"mismatch_samples": mismatches[:20],
		"quantity_and_rate_comparison": "Exact decimal grouped quantity, final rate and frozen source rate; no rounding allowance",
		"derived_amount_comparison": "sum(qty × rate), with 0.000001 arithmetic tolerance; original amounts independently retained/audited",
		"field_dispositions": {
			"item": "natural grouping key; compared",
			"lot": "natural grouping key; compared",
			"item_group": "copied or target-derived when source blank",
			"expense_head": "group invariant; compared",
			"qty": "summed per natural group; compared",
			"uom": "natural grouping key; compared",
			"rate": "group invariant/final rate; compared",
			"amount": "recomputed as sum(qty × rate); compared",
			"tax": "natural grouping key; compared",
			"actual_rate": "represented as source_rate with reviewed fallback; compared",
			"actual_qty": "PO rows retained directly; all WO values are zero and have no grouped column",
		},
	}


def _summarize(auditor: Auditor, auth: Mapping[str, Any], pi: Mapping[str, Any]):
	fields = [metric.payload() for metric in auditor.metrics.values()]
	return {
		"source_doctypes": len(auditor.plan.specs),
		"source_schema_fields": sum(
			len(_schema_fields(spec.source_schema)) for spec in auditor.plan.specs.values()
		),
		"field_routes": len(fields),
		"source_rows_read": auditor.total_source_rows,
		"direct_rows_compared": auditor.total_compared_rows,
		"source_field_values_seen": sum(row["source_values_seen"] for row in fields),
		"source_nonblank_field_values": sum(row["source_nonblank_values"] for row in fields),
		"source_material_field_values": sum(row["source_material_values"] for row in fields),
		"compared_field_values": sum(row["compared_values"] for row in fields),
		"exact_matches": sum(row["exact_matches"] for row in fields),
		"normalized_matches": sum(row["normalized_matches"] for row in fields),
		"target_fills_from_source_blank": sum(
			row["target_filled_from_source_blank"] for row in fields
		),
		"verified_default_fills": sum(row["verified_default_fills"] for row in fields),
		"unverified_default_fills": sum(
			row["target_filled_from_source_blank"] - row["verified_default_fills"] for row in fields
		),
		"mismatched_field_values": sum(row["mismatches"] for row in fields),
		"missing_target_row_field_values": sum(row["missing_target_rows"] for row in fields),
		"field_routes_with_mismatches": sum(row["status"] == "Mismatch" for row in fields),
		"ignored_field_routes_with_material_data": sum(
			row["status"] == "Ignored With Material Data" for row in fields
		),
		"schema_gap_routes": sum(row["status"] == "Schema Gap" for row in fields),
		"missing_auth_rows": int(auth["missing_expected_rows"]),
		"ignored_auth_rows_with_data": int(auth["ignored_rows_with_data"]),
		"purchase_invoice_group_mismatches": int(pi["mismatch_count"]),
	}


def _audit_source_archives(plan, source_db, target_db):
	"""Compare raw archived row values directly to SQL, without a transformer."""
	results = []
	for parent, child, parentfield, archive_field in (
		("Item Production Detail", "IPD Process", "ipd_processes", "original_process_rows"),
	):
		with source_db.cursor() as cursor:
			cursor.execute(f"SELECT name FROM {_quote('tab' + parent)} ORDER BY name")
			names = [row["name"] for row in cursor.fetchall()]
		fields = _schema_fields(plan.specs[child].source_schema)
		checked_rows = checked_values = 0
		failures = []
		for offset in range(0, len(names), 500):
			batch = names[offset:offset + 500]
			placeholders = ",".join(["%s"] * len(batch))
			with source_db.cursor() as cursor:
				cursor.execute(
					f"SELECT * FROM {_quote('tab' + child)} WHERE parenttype=%s AND parentfield=%s "
					f"AND parent IN ({placeholders}) ORDER BY parent, idx, name",
					[parent, parentfield, *batch],
				)
				source_rows = defaultdict(list)
				for row in cursor.fetchall():
					source_rows[row["parent"]].append(row)
			with target_db.cursor() as cursor:
				cursor.execute(
					f"SELECT name, {_quote(archive_field)} FROM {_quote('tab' + plan.specs[parent].target)} "
					f"WHERE name IN ({placeholders})", batch,
				)
				targets = {row["name"]: row[archive_field] for row in cursor.fetchall()}
			for name in batch:
				try:
					archived = json.loads(targets.get(name) or "null")
				except (ValueError, TypeError):
					archived = None
				if not isinstance(archived, list):
					failures.append(f"{parent} {name}: missing/invalid {archive_field}")
					continue
				by_name = {row.get("name"): row for row in archived}
				if len(by_name) != len(archived) or set(by_name) != {r["name"] for r in source_rows[name]}:
					failures.append(f"{parent} {name}: archived row identities differ")
				for row in source_rows[name]:
					actual = by_name.get(row["name"], {})
					checked_rows += 1
					for fieldname, value in row.items():
						if fieldname not in fields and fieldname not in SYSTEM_FIELDS:
							continue
						fieldtype = fields.get(fieldname, {}).get("fieldtype", "System")
						checked_values += 1
						if fieldname not in actual or _compare_values(value, actual[fieldname], fieldtype, None) != "exact":
							failures.append(f"{parent} {name}/{row['name']}.{fieldname}: archived value differs")
		results.append({"source_parent": parent, "archive_field": archive_field,
			"parents": len(names), "source_rows": checked_rows, "values": checked_values,
			"mismatch_count": len(failures), "samples": failures[:100]})
	return {"mismatch_count": sum(r["mismatch_count"] for r in results), "tables": results}


def _audit_retired_tables(source_db, target_db, migration_name, *, source_site_path=None):
	"""Independently inspect raw retired tables and the persisted target archive."""
	with target_db.cursor() as cursor:
		cursor.execute("SELECT retired_source_rows_json FROM `tabSD YRP MRP Data Migration` WHERE name=%s", (migration_name,))
		stored = cursor.fetchone()
	try:
		archive = json.loads((stored or {}).get("retired_source_rows_json") or "null")
	except (ValueError, TypeError):
		archive = None
	if not isinstance(archive, list):
		return {"mismatch_count": 1, "tables": [], "samples": ["Missing retired-table archive"]}
	by_key = {(r.get("source_doctype"), r.get("row", {}).get("name")): r.get("row", {}) for r in archive}
	failures = [] if len(by_key) == len(archive) else ["Duplicate retired-table archive identity"]
	remaining = set(by_key)
	tables = []
	retired_names = ("WO Debit", "Employee Department", "Item Production Detail Cloth Accessories", "Custom User Dashboard", "Custom User Dashboard User")
	for doctype in (*retired_names, "File"):
		with source_db.cursor() as cursor:
			cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name=%s", ("tab"+doctype,))
			if not cursor.fetchone():
				continue
			if doctype == "File":
				cursor.execute("SELECT * FROM tabFile WHERE attached_to_doctype IN %s ORDER BY name", (retired_names,))
			else:
				cursor.execute(f"SELECT * FROM {_quote('tab' + doctype)} ORDER BY name")
			rows = cursor.fetchall()
		values = 0
		before = len(failures)
		for row in rows:
			key = (doctype, row["name"])
			remaining.discard(key)
			actual = by_key.get(key, {})
			if set(actual) != set(row):
				failures.append(f"{doctype} {row['name']}: archived columns differ")
			for fieldname, value in row.items():
				values += 1
				fieldtype = "Float" if isinstance(value, decimal.Decimal) else "System"
				if fieldname not in actual or _compare_values(value, actual[fieldname], fieldtype, None) != "exact":
					failures.append(f"{doctype} {row['name']}.{fieldname}: archived value differs")
		tables.append({"source_doctype": doctype, "rows": len(rows), "values": values, "mismatch_count": len(failures)-before})
	failures.extend(f"Unexpected archived identity {dt} {name}" for dt, name in sorted(remaining))
	missing_blobs = []
	verified_blobs = 0
	source_blobs = None
	checked_source_blobs = available_source_blobs = 0
	for record in archive:
		if record.get("source_doctype") != "File":
			continue
		row = record["row"]
		if source_blobs is None:
			from audit_attachment_values import SourceBlobEvidence

			source_blobs = SourceBlobEvidence(source_db, source_site_path)
		available = source_blobs.available(row)
		checked_source_blobs += 1
		available_source_blobs += int(available)
		if not available:
			missing_blobs.append({"name": row["name"], "issue": "Source bytes unavailable/corrupt in independent disk check"})
		if record.get("blob_issue"):
			if available:
				failures.append(f"Retired File {row['name']}: available source bytes incorrectly archived as missing")
			continue
		try:
			content = base64.b64decode(record["blob_base64"], validate=True)
			matches = len(content) == int(row["file_size"]) and hashlib.md5(content).hexdigest() == row["content_hash"]
		except (KeyError, ValueError, TypeError):
			matches = False
		if not matches:
			failures.append(f"Retired File {row['name']}: archived blob differs")
		else:
			verified_blobs += 1
	return {"mismatch_count": len(failures), "tables": tables, "samples": failures[:100],
		"independently_checked_source_blobs": checked_source_blobs, "available_source_blobs": available_source_blobs,
		"missing_source_blobs": missing_blobs, "verified_blobs": verified_blobs}


def _audit_debit_discriminator(source_db):
	with source_db.cursor() as cursor:
		cursor.execute("SELECT `against`, COUNT(*) AS n FROM `tabEssdee Debit` GROUP BY `against`")
		rows = cursor.fetchall()
	return {
		"source_doctype": "Essdee Debit", "source_field": "against",
		"target_representation": "YRP Debit.work_order",
		"source_values": [{"value": row["against"], "count": row["n"]} for row in rows],
		"unsupported_rows": sum(row["n"] for row in rows if row["against"] not in (None, "", "Work Order")),
		"link_values_audited_in_field_route": "against_id -> work_order",
	}


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--site", required=True)
	parser.add_argument("--bench", type=Path, default=Path(__file__).resolve().parents[3])
	parser.add_argument("--output", type=Path, required=True)
	parser.add_argument("--batch-size", type=int, default=500)
	parser.add_argument("--doctypes-json")
	parser.add_argument("--migration", required=True, help="Exact target migration audit record holding retired source rows")
	args = parser.parse_args()
	bench = args.bench.resolve()
	output = args.output.resolve()
	sys.path.insert(0, str(bench / "apps"))
	# Frappe's file logger resolves ``<site>/logs`` relative to the sites
	# directory, matching the working directory used by bench commands.
	os.chdir(bench / "sites")

	import frappe

	frappe.init(site=args.site, sites_path=str(bench / "sites"))
	frappe.connect()
	try:
		from essdee_yrp.migration.config import get_migration_settings
		from essdee_yrp.migration.live import F15SourceBridge, build_live_schema_analysis

		settings = get_migration_settings()
		source_bridge = F15SourceBridge(settings)
		plan, schema_payload = build_live_schema_analysis(settings, source_bridge)
		if not plan.ready:
			raise RuntimeError("Migration plan is blocked: " + "; ".join(plan.issues))
		requested = set(json.loads(args.doctypes_json)) if args.doctypes_json else None
		source_db = _connect(settings.source_bench, settings.source_site)
		target_db = _connect(bench, args.site)
		try:
			auditor = Auditor(plan, source_db, target_db, max(1, args.batch_size),
				configured_defaults=settings.required_defaults)
			child_routes = _child_routes(plan)
			inferred_child_routes = []
			for source_doctype in sorted(plan.specs):
				if requested and source_doctype not in requested:
					continue
				spec = plan.specs[source_doctype]
				if spec.source_schema.get("istable"):
					routes = list(child_routes.get(source_doctype) or [])
					declared_keys = {
						(route.source_parenttype, route.source_parentfield) for route in routes
					}
					for stored_route in _stored_child_routes(plan, source_db, source_doctype):
						key = (
							stored_route.source_parenttype,
							stored_route.source_parentfield,
						)
						if key in declared_keys:
							continue
						routes.append(stored_route)
						inferred_child_routes.append(
							{
								"source_doctype": source_doctype,
								"source_context": stored_route.label,
								"target_doctype": stored_route.target_doctype,
								"target_context": (
									f"{stored_route.target_parenttype}."
									f"{stored_route.target_parentfield}"
								),
								"reason": "stored child context absent from current parent metadata",
							}
						)
					if not routes:
						# Retain a zero-row schema disposition even for an unused child
						# DocType. If undeclared rows ever appear, the unscoped direct
						# route also prevents them from escaping the audit.
						routes.append(Route(source_doctype, spec.target))
					for route in routes:
						auditor.audit_route(route)
				else:
					auditor.audit_route(Route(source_doctype, spec.target))
			auth = _audit_auth(plan, source_db, target_db,
				source_key=_load_site_config(settings.source_bench, settings.source_site).get("encryption_key"),
				target_key=_load_site_config(bench, args.site).get("encryption_key"))
			pi = _audit_purchase_invoice_projection(
				source_db, target_db, auditor.wo_invoice_names
			)
			from audit_invoice_grn_values import audit_invoice_grn_values

			physical_pi = audit_invoice_grn_values(source_db, target_db, auditor.wo_invoice_names)
			from audit_bin_reservations import audit_bin_reservations

			reservations = audit_bin_reservations(source_db, target_db)
			archives = _audit_source_archives(plan, source_db, target_db)
			retired = _audit_retired_tables(source_db, target_db, args.migration,
				source_site_path=settings.source_bench / 'sites' / settings.source_site)
			from audit_attachment_values import audit_attachments

			attachments = audit_attachments(source_db, target_db, plan,
				settings.source_bench / 'sites' / settings.source_site, bench / 'sites' / args.site)
			from audit_framework_values import audit_framework

			framework = audit_framework(source_db, target_db, plan, args.migration,
				bench / 'sites' / args.site,
				_load_site_config(bench, args.site).get('encryption_key'),
				source_site_path=settings.source_bench / 'sites' / settings.source_site)
			debit = _audit_debit_discriminator(source_db)
			# Operational readiness of NEW valuation links is separate from
			# original-source-value parity. Keep unresolved history visible even
			# after the migration screen replaces its Migrate report with Verify.
			from essdee_yrp.patches.backfill_deterministic_valuation_lineage import get_valuation_lineage_readiness

			valuation_readiness = get_valuation_lineage_readiness()
			field_results = sorted(
				(metric.payload() for metric in auditor.metrics.values()),
				key=lambda row: (
					row["source_doctype"],
					row["context"],
					row["source_field"],
					row["target_doctype"],
				),
			)
			payload = {
				"generated_on": dt.datetime.now().astimezone().isoformat(),
				"read_only": True,
				"complete_application_scope": requested is None or requested == set(plan.specs),
				"requested_doctypes": sorted(requested) if requested is not None else None,
				"source": {
					"bench": str(settings.source_bench),
					"site": settings.source_site,
					"app": settings.source_app,
				},
				"target": {
					"bench": str(bench),
					"site": args.site,
					"apps": list(settings.target_apps),
				},
				"method": (
					"Direct source/target SQL by source identity; reviewed routing only; "
					"transform_document was not used to generate expected rows"
				),
				"plan_ready": plan.ready,
				"plan_issue_count": len(plan.issues),
				"schema_payload_counts": {
					"source_doctypes": schema_payload.get("source_doctypes"),
					"target_doctypes": schema_payload.get("target_doctypes"),
				},
				"summary": _summarize(auditor, auth, pi),
				"document_routes": auditor.documents,
				"inferred_child_routes": inferred_child_routes,
				"field_results": field_results,
				"auth": auth,
				"purchase_invoice_projection": pi,
				"purchase_invoice_physical_grns": physical_pi,
				"bin_reservations": reservations,
				"raw_source_archives": archives,
				"retired_source_archives": retired,
				"attachments": attachments,
				"framework_history": framework,
				"migration_name": args.migration,
				"debit_discriminator": debit,
				"valuation_lineage_readiness": valuation_readiness,
			}
			payload["summary"]["raw_source_archive_mismatches"] = archives["mismatch_count"]
			payload["summary"]["credential_value_mismatches"] = auth["value_mismatches"]
			payload["summary"]["credential_record_identity_mismatches"] = auth["record_identity_mismatches"]
			payload["summary"]["purchase_invoice_physical_grn_mismatches"] = physical_pi["mismatch_count"]
			payload["summary"]["bin_reservation_mismatches"] = reservations["mismatch_count"]
			payload["summary"]["retired_source_archive_mismatches"] = retired["mismatch_count"]
			payload["summary"]["framework_value_mismatches"] = framework["mismatch_count"]
			payload["summary"]["attachment_value_mismatches"] = attachments["mismatch_count"]
			payload["summary"]["unsupported_debit_discriminators"] = debit["unsupported_rows"]
			output.parent.mkdir(parents=True, exist_ok=True)
			output.write_text(
				json.dumps(payload, indent=2, default=str), encoding="utf-8"
			)
			print(json.dumps(payload["summary"], indent=2))
		finally:
			source_db.close()
			target_db.close()
	finally:
		frappe.destroy()
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
