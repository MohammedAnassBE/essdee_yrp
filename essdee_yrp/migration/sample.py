"""Capped, query-only Production API sample migration and SQL read-back audit."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

import frappe
from frappe.utils import now_datetime

from essdee_yrp.migration.engine import MigrationError, transform_document
from essdee_yrp.migration.live import (
	F15SourceBridge,
	FrappeBulkTarget,
	TABLE_FIELD_TYPES,
	_db_value,
	_quote_identifier,
	_resolve_and_validate_required_target_values,
	_validate_external_references,
	_validate_live_target_metadata,
	build_live_schema_analysis,
)
from essdee_yrp.migration.config import get_migration_settings


MAX_SAMPLE_PER_DOCTYPE = 20
NUMERIC_FIELD_TYPES = {"Check", "Currency", "Float", "Int", "Percent"}


def audit_full_external_references() -> dict[str, Any]:
	"""Read every source Link and report full-migration external blockers."""

	settings = get_migration_settings()
	if frappe.local.site != settings.target_site:
		raise MigrationError(f"Reference audit must run on {settings.target_site}")
	source = F15SourceBridge(settings)
	plan, _payload = build_live_schema_analysis(settings, source)
	if not plan.ready:
		return {"status": "Blocked", "issues": list(plan.issues)}
	try:
		checked, missing = _validate_external_references(plan, source)
	except MigrationError as exc:
		return {"status": "Failed", "error": str(exc)}
	return {
		"status": "Pass",
		"checked": checked,
		"supporting_external_to_copy": {
			doctype: len(names) for doctype, names in sorted(missing.items())
		},
	}


class QueryOnlySampleTarget(FrappeBulkTarget):
	"""Historical sample writer restricted to SQL; no Document insert/save hooks."""

	def existing_names(self, target_doctype: str, names: list[str]) -> set[str]:
		if not names:
			return set()
		meta = frappe.get_meta(target_doctype)
		if meta.issingle:
			rows = frappe.db.sql(
				"SELECT 1 FROM `tabSingles` WHERE `doctype`=%s LIMIT 1",
				(target_doctype,),
			)
			return {target_doctype} if rows else set()
		placeholders = ", ".join(["%s"] * len(names))
		rows = frappe.db.sql(
			f"SELECT `name` FROM {_quote_identifier('tab' + target_doctype)} "
			f"WHERE `name` IN ({placeholders})",
			names,
		)
		return {str(row[0]) for row in rows}

	def upsert_batch(self, target_doctype: str, documents: list[dict[str, Any]]) -> None:
		if not documents:
			return
		meta = frappe.get_meta(target_doctype)
		if meta.issingle:
			for document in documents:
				self._upsert_single_sql(meta, document)
			self._replace_child_tables_sql(meta, documents)
			return

		table_fields = {field.fieldname for field in meta.get_table_fields()}
		parent_rows = [
			{
				key: value
				for key, value in document.items()
				if key not in table_fields and key not in {"doctype", "__migration_passwords"}
			}
			for document in documents
		]
		self._bulk_upsert(target_doctype, parent_rows)
		self._replace_child_tables_sql(meta, documents)
		if target_doctype == 'YRP Supplier':
			self._upsert_supplier_warehouses(documents)

	def _upsert_single_sql(self, meta, document: Mapping[str, Any]) -> None:
		table_fields = {field.fieldname for field in meta.get_table_fields()}
		valid_fields = {
			field.fieldname
			for field in meta.fields
			if field.fieldname
			and field.fieldname not in table_fields
			and field.fieldtype not in TABLE_FIELD_TYPES
			and field.fieldtype != "Password"
		}
		rows = [
			(meta.name, fieldname, _db_value(value))
			for fieldname, value in document.items()
			if fieldname in valid_fields
		]
		if not rows:
			return
		placeholders = ", ".join(["(%s, %s, %s)"] * len(rows))
		values = [value for row in rows for value in row]
		frappe.db.sql(
			"INSERT INTO `tabSingles` (`doctype`, `field`, `value`) VALUES "
			+ placeholders
			+ " ON DUPLICATE KEY UPDATE `value`=VALUES(`value`)",
			values,
		)

	def _replace_child_tables_sql(self, meta, documents: list[dict[str, Any]]) -> None:
		for table_field in meta.get_table_fields():
			parents = [doc for doc in documents if table_field.fieldname in doc]
			if not parents:
				continue
			parent_names = [str(doc["name"]) for doc in parents]
			placeholders = ", ".join(["%s"] * len(parent_names))
			frappe.db.sql(
				f"DELETE FROM {_quote_identifier('tab' + table_field.options)} "
				"WHERE `parenttype`=%s AND `parentfield`=%s "
				f"AND `parent` IN ({placeholders})",
				[meta.name, table_field.fieldname, *parent_names],
			)
			child_rows = []
			for document in parents:
				for idx, child in enumerate(document.get(table_field.fieldname) or [], start=1):
					if child.get("doctype") != table_field.options:
						raise MigrationError(
							f"{meta.name}.{table_field.fieldname} expected "
							f"{table_field.options}, received {child.get('doctype')}"
						)
					if not child.get("name"):
						raise MigrationError(
							f"{table_field.options} row under {document['name']} has no source name"
						)
					row = {
						key: value
						for key, value in child.items()
						if key not in {"doctype", "__migration_passwords"}
					}
					row.update(
						{
							"parent": document["name"],
							"parenttype": meta.name,
							"parentfield": table_field.fieldname,
							"idx": idx,
						}
					)
					child_rows.append(row)
			self._bulk_upsert(table_field.options, child_rows)


def run_query_only_sample(
	migration_name: str,
	limit_per_doctype: int = MAX_SAMPLE_PER_DOCTYPE,
) -> dict[str, Any]:
	"""Write and SQL-verify up to 20 source parents per mapped DocType."""

	settings = get_migration_settings()
	if frappe.local.site != settings.target_site:
		raise MigrationError(f"Sample migration must run on {settings.target_site}")
	limit = int(limit_per_doctype)
	if limit < 1 or limit > MAX_SAMPLE_PER_DOCTYPE:
		raise MigrationError(
			f"Sample limit must be between 1 and {MAX_SAMPLE_PER_DOCTYPE}"
		)
	if not frappe.db.exists('SD YRP MRP Data Migration', migration_name):
		raise MigrationError(f"Unknown MRP Data Migration {migration_name}")

	source = F15SourceBridge(settings)
	plan, schema_payload = build_live_schema_analysis(settings, source)
	if not plan.ready:
		raise MigrationError("Schema plan is blocked:\n" + "\n".join(plan.issues))
	_validate_live_target_metadata(plan)
	source_status = source.status()
	if source_status.get("site") != settings.source_site:
		raise MigrationError("Source bridge connected to an unapproved site")

	target = QueryOnlySampleTarget()
	reference_data = source.reference_data()
	report: dict[str, Any] = {
		"mode": "query_only_sample",
		"source_site": settings.source_site,
		"target_site": settings.target_site,
		"limit_per_parent_doctype": limit,
		"schema": {
			"source_doctypes": schema_payload["source_doctypes"],
			"target_doctypes": schema_payload["target_doctypes"],
			"issues": schema_payload["issue_count"],
		},
		"attachments": "Not sampled; File transport is not query-only",
		"naming_series": "Not changed by sample migration",
		"doctypes": [],
		"issues": [],
	}
	_mark_sample_started(migration_name, plan, source_status, limit)
	stored_documents: list[dict[str, Any]] = []
	sampled_names: dict[str, set[str]] = defaultdict(set)
	totals = defaultdict(int)

	for index, source_doctype in enumerate(plan.parent_doctypes):
		spec = plan.specs[source_doctype]
		savepoint = f"mrp_sample_{index}"
		frappe.db.savepoint(savepoint)
		row = {
			"source_doctype": source_doctype,
			"target_doctype": spec.target,
			"source_total": int(
				(source_status.get("doctype_counts") or {}).get(source_doctype) or 0
			),
			"sampled_parents": 0,
			"sampled_children": 0,
			"inserted_parents": 0,
			"updated_parents": 0,
			"verified_field_values": 0,
			"skipped_password_values": 0,
			"status": "Pending",
			"issues": [],
		}
		try:
			source_documents = list(
				source.iter_documents(
					source_doctype,
					batch_size=limit,
					limit=limit,
				)
			)
			target_documents = []
			for source_document in source_documents:
				target_document = transform_document(source_document, plan)
				row["skipped_password_values"] += _strip_password_values(target_document)
				_resolve_and_validate_required_target_values(
					target_document,
					plan,
					reference_data=reference_data,
				)
				target_documents.append(target_document)

			existing = target.existing_names(
				spec.target,
				[doc["name"] for doc in target_documents],
			)
			target.upsert_batch(spec.target, target_documents)
			verification = _verify_documents_sql(target_documents, plan)
			if verification["issues"]:
				raise MigrationError("; ".join(verification["issues"][:20]))

			frappe.db.commit()
			row["sampled_parents"] = len(target_documents)
			row["sampled_children"] = verification["child_rows"]
			row["inserted_parents"] = len(target_documents) - len(existing)
			row["updated_parents"] = len(existing)
			row["verified_field_values"] = verification["field_values"]
			row["status"] = "Pass"
			stored_documents.extend(target_documents)
			for document in target_documents:
				_collect_names(document, plan, sampled_names)
		except Exception as exc:
			frappe.db.rollback(save_point=savepoint)
			row["status"] = "Failed"
			row["issues"].append(str(exc))
			report["issues"].append(f"{source_doctype}: {exc}")
		report["doctypes"].append(row)
		for key in (
			"sampled_parents",
			"sampled_children",
			"inserted_parents",
			"updated_parents",
			"verified_field_values",
			"skipped_password_values",
		):
			totals[key] += int(row[key])
		_update_sample_progress(migration_name, totals["sampled_parents"], len(report["issues"]))

	report["link_audit"] = _audit_sample_links(
		stored_documents,
		plan,
		sampled_names,
		source_status.get("doctype_counts") or {},
		limit,
	)
	report["totals"] = dict(totals)
	report["failed_doctypes"] = sum(
		1 for row in report["doctypes"] if row["status"] == "Failed"
	)
	report["status"] = "Pass" if not report["issues"] else "Failed"
	_mark_sample_complete(migration_name, report)
	return report


def _strip_password_values(document: dict[str, Any]) -> int:
	count = len(document.pop("__migration_passwords", {}) or {})
	for value in document.values():
		if isinstance(value, list):
			for child in value:
				if isinstance(child, dict) and child.get("doctype"):
					count += _strip_password_values(child)
	return count


def _verify_documents_sql(documents, plan) -> dict[str, Any]:
	result = {"field_values": 0, "child_rows": 0, "issues": []}
	for document in documents:
		_verify_document_sql(document, plan, result)
	return result


def _verify_document_sql(document, plan, result, *, parent_context=None) -> None:
	doctype = str(document["doctype"])
	schema = plan.target_schemas[doctype]
	field_by_name = {
		field["fieldname"]: field
		for field in schema.get("fields") or []
		if field.get("fieldname")
	}
	table_fields = {
		name: field
		for name, field in field_by_name.items()
		if field.get("fieldtype") in TABLE_FIELD_TYPES
	}

	if schema.get("issingle"):
		actual = dict(
			frappe.db.sql(
				"SELECT `field`, `value` FROM `tabSingles` WHERE `doctype`=%s",
				(doctype,),
			)
		)
	else:
		columns = set(frappe.db.get_table_columns(doctype))
		expected = {
			key: value
			for key, value in document.items()
			if key in columns and key not in table_fields and key != "__migration_passwords"
		}
		if parent_context:
			expected.update(parent_context)
		fields = list(expected)
		select_fields = ", ".join(_quote_identifier(field) for field in fields)
		rows = frappe.db.sql(
			f"SELECT {select_fields} FROM {_quote_identifier('tab' + doctype)} WHERE `name`=%s",
			(document["name"],),
			as_dict=True,
		)
		if len(rows) != 1:
			result["issues"].append(f"{doctype} {document['name']} was not stored exactly once")
			return
		actual = rows[0]

	values_to_compare = dict(document)
	if parent_context:
		values_to_compare.update(parent_context)
	for fieldname, expected_value in values_to_compare.items():
		if schema.get("issingle") and fieldname not in field_by_name:
			# Single values live in tabSingles; document audit/system values are
			# not Single fields and must not be compared with stale tabSingles rows.
			continue
		if fieldname in table_fields or fieldname in {"doctype", "__migration_passwords"}:
			continue
		if fieldname not in actual:
			continue
		fieldtype = (field_by_name.get(fieldname) or {}).get("fieldtype")
		if not _same_db_value(expected_value, actual[fieldname], fieldtype):
			result["issues"].append(
				f"{doctype} {document['name']}.{fieldname}: "
				f"expected={expected_value!r}, stored={actual[fieldname]!r}"
			)
		result["field_values"] += 1

	for fieldname, table_field in table_fields.items():
		# A target-only child table is intentionally preserved. Only replace and
		# verify a table when the transformed source document carries that field.
		if fieldname not in document:
			continue
		children = document.get(fieldname) or []
		actual_names = {
			row[0]
			for row in frappe.db.sql(
				f"SELECT `name` FROM {_quote_identifier('tab' + table_field['options'])} "
				"WHERE `parent`=%s AND `parenttype`=%s AND `parentfield`=%s",
				(document["name"], doctype, fieldname),
			)
		}
		expected_names = {str(child["name"]) for child in children}
		if actual_names != expected_names:
			result["issues"].append(
				f"{doctype} {document['name']}.{fieldname} child identities differ"
			)
			continue
		for idx, child in enumerate(children, start=1):
			result["child_rows"] += 1
			_verify_document_sql(
				child,
				plan,
				result,
				parent_context={
					"parent": document["name"],
					"parenttype": doctype,
					"parentfield": fieldname,
					"idx": idx,
				},
			)


def _same_db_value(expected, actual, fieldtype) -> bool:
	expected = _db_value(expected)
	if expected is None or actual is None:
		return expected is None and actual is None
	if fieldtype in NUMERIC_FIELD_TYPES:
		try:
			return Decimal(str(expected or 0)) == Decimal(str(actual or 0))
		except InvalidOperation:
			return False
	if fieldtype == "JSON":
		try:
			left = json.loads(expected) if isinstance(expected, str) else expected
			right = json.loads(actual) if isinstance(actual, str) else actual
			return left == right
		except (TypeError, ValueError):
			pass
	if isinstance(expected, (date, datetime, time)):
		expected = str(expected)
	if isinstance(actual, (date, datetime, time)):
		actual = str(actual)
	return str(expected) == str(actual)


def _collect_names(document, plan, sampled_names) -> None:
	sampled_names[str(document["doctype"])].add(str(document["name"]))
	schema = plan.target_schemas[str(document["doctype"])]
	for field in schema.get("fields") or []:
		if field.get("fieldtype") not in TABLE_FIELD_TYPES:
			continue
		for child in document.get(str(field.get("fieldname"))) or []:
			_collect_names(child, plan, sampled_names)


def _audit_sample_links(documents, plan, sampled_names, source_counts, limit):
	target_source_counts = defaultdict(int)
	for source_doctype, spec in plan.specs.items():
		target_source_counts[spec.target] += int(source_counts.get(source_doctype) or 0)
	missing_sample_only = defaultdict(lambda: {"count": 0, "samples": []})
	missing_required = defaultdict(lambda: {"count": 0, "samples": []})

	def inspect(document):
		doctype = str(document["doctype"])
		schema = plan.target_schemas[doctype]
		for field in schema.get("fields") or []:
			fieldname = field.get("fieldname")
			if not fieldname:
				continue
			if field.get("fieldtype") in TABLE_FIELD_TYPES:
				for child in document.get(fieldname) or []:
					inspect(child)
				continue
			value = document.get(fieldname)
			if value in (None, ""):
				continue
			linked_doctype = None
			if field.get("fieldtype") == "Link":
				linked_doctype = field.get("options")
			elif field.get("fieldtype") == "Dynamic Link":
				linked_doctype = document.get(str(field.get("options")))
			if not linked_doctype or not _table_exists(linked_doctype):
				continue
			if _name_exists(linked_doctype, value):
				continue
			key = f"{doctype}.{fieldname} -> {linked_doctype}"
			expected_unsampled = (
				linked_doctype in sampled_names
				and str(value) not in sampled_names[linked_doctype]
				and target_source_counts[linked_doctype] > limit
			)
			bucket = missing_sample_only if expected_unsampled else missing_required
			bucket[key]["count"] += 1
			if len(bucket[key]["samples"]) < 5:
				bucket[key]["samples"].append(f"{document['name']}={value}")

	for document in documents:
		inspect(document)
	return {
		"expected_missing_due_to_20_record_cap": dict(missing_sample_only),
		"unexpected_missing_links": dict(missing_required),
	}


def _table_exists(doctype: str) -> bool:
	rows = frappe.db.sql("SHOW TABLES LIKE %s", ("tab" + str(doctype),))
	return bool(rows)


def _name_exists(doctype: str, name: Any) -> bool:
	rows = frappe.db.sql(
		f"SELECT 1 FROM {_quote_identifier('tab' + str(doctype))} WHERE `name`=%s LIMIT 1",
		(name,),
	)
	return bool(rows)


def _mark_sample_started(migration_name, plan, source_status, limit) -> None:
	frappe.db.sql(
		"""
		UPDATE `tabSD YRP MRP Data Migration`
		SET `status`='Running', `last_action`='Sample', `last_started_on`=%s,
			`last_completed_on`=NULL, `total_source_records`=%s,
			`processed_records`=0, `skipped_records`=0, `failed_records`=0,
			`error_log`=NULL
		WHERE `name`=%s
		""",
		(
			now_datetime(),
			sum(
				min(int((source_status.get("doctype_counts") or {}).get(dt) or 0), limit)
				for dt in plan.parent_doctypes
			),
			migration_name,
		),
	)
	frappe.db.commit()


def _update_sample_progress(migration_name, processed, failed) -> None:
	frappe.db.sql(
		"UPDATE `tabSD YRP MRP Data Migration` SET `processed_records`=%s, `failed_records`=%s "
		"WHERE `name`=%s",
		(processed, failed, migration_name),
	)
	frappe.db.commit()


def _mark_sample_complete(migration_name, report) -> None:
	frappe.db.sql(
		"""
		UPDATE `tabSD YRP MRP Data Migration`
		SET `status`=%s, `last_completed_on`=%s, `processed_records`=%s,
			`failed_records`=%s, `report_json`=%s, `error_log`=%s
		WHERE `name`=%s
		""",
		(
			"Sample Complete" if report["status"] == "Pass" else "Failed",
			now_datetime(),
			report["totals"].get("sampled_parents", 0),
			report["failed_doctypes"],
			json.dumps(report, sort_keys=True, default=str),
			"\n".join(report["issues"]) or None,
			migration_name,
		),
	)
	frappe.db.commit()
