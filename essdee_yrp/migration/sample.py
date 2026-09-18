"""Capped, query-only Production API sample migration and SQL read-back audit."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Mapping

import frappe
from frappe.utils import now_datetime

from essdee_yrp.migration.engine import MigrationError, transform_document
from essdee_yrp.migration.live import (
	F15SourceBridge,
	FrappeBulkTarget,
	SUPPORTING_EXTERNAL_DOCTYPE_ORDER,
	TABLE_FIELD_TYPES,
	_assert_approved_frappe_child_identities,
	_db_value,
	_ensure_standard_item_attribute_value_pairs,
	_ensure_supporting_masters,
	_load_supporting_external_masters,
	_migration_physical_target_doctypes,
	_prepare_approved_frappe_document,
	_prepare_item_migration_documents,
	_prepare_purchase_invoice_migration_documents,
	_quote_identifier,
	_reconcile_approved_default_values,
	_reconcile_approved_user_unique_values,
	_resolve_and_validate_required_target_values,
	_run_series,
	_source_broken_link_manifest,
	_transform_supporting_document,
	_validate_external_references,
	_validate_live_target_metadata,
	_verify_link_integrity,
	build_live_schema_analysis,
)
from essdee_yrp.migration.config import get_migration_settings
from essdee_yrp.migration.locking import exclusive_migration_run


MAX_SAMPLE_PER_DOCTYPE = 20
DEFAULT_PERCENTAGE_SAMPLE = 25
MAX_PERCENTAGE_SAMPLE = 25
DEFAULT_SAMPLE_BATCH_SIZE = 250
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
		if target_doctype == "Item Attribute Value":
			self._reconcile_item_attribute_values(documents)
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
		if target_doctype == 'Supplier':
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
		fieldnames = [row[1] for row in rows]
		field_placeholders = ", ".join(["%s"] * len(fieldnames))
		# tabSingles has only a non-unique lookup index in Frappe.  SQL
		# ``ON DUPLICATE KEY`` therefore inserts a second value instead of
		# replacing the fresh-site default.  Delete the exact incoming fields first
		# so this query-only writer has the same semantics as set_single_value().
		frappe.db.sql(
			"DELETE FROM `tabSingles` WHERE `doctype`=%s "
			f"AND `field` IN ({field_placeholders})",
			[meta.name, *fieldnames],
		)
		placeholders = ", ".join(["(%s, %s, %s)"] * len(rows))
		values = [value for row in rows for value in row]
		frappe.db.sql(
			"INSERT INTO `tabSingles` (`doctype`, `field`, `value`) VALUES "
			+ placeholders,
			values,
		)
		# get_single_value() caches each field in-process.  Analyse reads the
		# fresh-site defaults before this SQL-only writer replaces them, so leaving
		# that cache populated makes dependency closure see the old blank values.
		# The final audit then reads the migrated values after another operation has
		# happened to clear the cache, producing a late broken-Link failure.  Mirror
		# Database.set_single_value() and invalidate the Single immediately.
		frappe.clear_document_cache(meta.name, meta.name)

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
					# Most transformed children preserve their source identity. A small
					# number of reviewed projections (currently grouped PI rows) are new
					# target rows and therefore have no source name. Give those rows the
					# same target-generated identity semantics as the full bulk writer,
					# while mutating the in-memory row so SQL read-back can verify it.
					if not child.get("name"):
						child["name"] = frappe.generate_hash(length=10)
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


@exclusive_migration_run
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
				_resolve_and_validate_required_target_values(
					target_document,
					plan,
					reference_data=reference_data,
				)
				row["skipped_password_values"] += _strip_password_values(target_document)
				target_documents.append(target_document)
			if source_doctype in {"Item", "Item Variant"}:
				target_documents = _prepare_item_migration_documents(
					source_doctype, target_documents
				)

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


@exclusive_migration_run
def run_query_only_percentage_sample(
	migration_name: str,
	percentage: int = DEFAULT_PERCENTAGE_SAMPLE,
	batch_size: int = DEFAULT_SAMPLE_BATCH_SIZE,
) -> dict[str, Any]:
	"""Migrate and SQL-verify a deterministic percentage of every parent DocType.

	The source bridge applies the cap to parent rows only. Every selected parent's
	complete child collection is transformed, stored, and compared field-by-field.
	The implementation is intentionally streaming so the 25% rehearsal cannot
	accumulate hundreds of thousands of documents in worker memory.
	"""

	settings = get_migration_settings()
	if frappe.local.site != settings.target_site:
		raise MigrationError(f"Sample migration must run on {settings.target_site}")
	percentage = int(percentage)
	if percentage < 1 or percentage > MAX_PERCENTAGE_SAMPLE:
		raise MigrationError(
			f"Percentage sample must be between 1 and {MAX_PERCENTAGE_SAMPLE}"
		)
	batch_size = max(1, min(int(batch_size), 1000))
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

	source_counts = {
		str(doctype): int(count or 0)
		for doctype, count in (source_status.get("doctype_counts") or {}).items()
	}
	limits = {
		doctype: _percentage_limit(source_counts.get(doctype, 0), percentage)
		for doctype in plan.parent_doctypes
	}
	target = QueryOnlySampleTarget()
	reference_data = source.reference_data()
	report: dict[str, Any] = {
		"mode": "query_only_percentage_sample",
		"percentage": percentage,
		"source_site": settings.source_site,
		"target_site": settings.target_site,
		"batch_size": batch_size,
		"schema": {
			"source_doctypes": schema_payload["source_doctypes"],
			"target_doctypes": schema_payload["target_doctypes"],
			"issues": schema_payload["issue_count"],
		},
		"attachments": "Excluded from this rehearsal by owner instruction",
		"naming_series": "Source counters are synchronized for entry-level rehearsal",
		"supporting_business_masters": [],
		"approved_frappe_data": [],
		"doctypes": [],
		"issues": [],
	}
	requested_total = sum(limits.values())
	_mark_percentage_sample_started(migration_name, requested_total)
	_ensure_supporting_masters(target, reference_data)
	frappe.db.commit()

	# Address and Contact are complete source-site business inventories outside
	# the Production API schema graph. Sample them explicitly, including all
	# Dynamic Link child rows belonging to each selected parent.
	_do_percentage_supporting_business_masters(
		source,
		target,
		plan,
		source_status,
		percentage,
		batch_size,
		report,
	)
	_do_percentage_approved_frappe_data(
		source,
		target,
		plan,
		source_status,
		percentage,
		batch_size,
		report,
	)
	if report["issues"]:
		report["totals"] = {}
		report["failed_doctypes"] = 0
		report["status"] = "Failed"
		_mark_sample_complete(migration_name, report)
		return report

	totals = defaultdict(int)
	# PI Work Order projection reads linked GRNs from the target. Defer PI until
	# every other sampled business DocType has been written.
	ordered_doctypes = [
		doctype for doctype in plan.parent_doctypes if doctype != "Purchase Invoice"
	]
	if "Purchase Invoice" in plan.parent_doctypes:
		ordered_doctypes.append("Purchase Invoice")
	for source_doctype in ordered_doctypes:
		spec = plan.specs[source_doctype]
		requested = limits[source_doctype]
		row = {
			"source_doctype": source_doctype,
			"target_doctype": spec.target,
			"source_total": source_counts.get(source_doctype, 0),
			"requested_parents": requested,
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
			batch: list[dict[str, Any]] = []
			for source_document in source.iter_documents(
				source_doctype,
				batch_size=batch_size,
				limit=requested,
			):
				document = transform_document(source_document, plan)
				_resolve_and_validate_required_target_values(
					document,
					plan,
					reference_data=reference_data,
				)
				row["skipped_password_values"] += _strip_password_values(document)
				batch.append(document)
				if len(batch) >= batch_size:
					_write_percentage_batch(
						source_doctype, spec.target, batch, target, plan, row
					)
					batch = []
			if batch:
				_write_percentage_batch(
					source_doctype, spec.target, batch, target, plan, row
				)
			if row["sampled_parents"] != requested:
				raise MigrationError(
					f"Source returned {row['sampled_parents']} of {requested} requested parents"
				)
			row["status"] = "Pass"
		except Exception as exc:
			# Percentage sampling commits every verified batch so very large source
			# DocTypes do not form one unbounded transaction. Roll back only the
			# current uncommitted batch; the report counts earlier committed batches,
			# and this disposable site must be reset before retrying a failed run.
			frappe.db.rollback()
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
		_update_sample_progress(
			migration_name, totals["sampled_parents"], len(report["issues"])
		)
		# A failed DocType invalidates the rehearsal. Stop immediately so a
		# large 25% run cannot spend hours loading later tables after its result
		# is already unusable; the returned report retains the exact first error.
		if row["status"] == "Failed":
			break

	if not report["issues"]:
		try:
			report["functional_dependencies"] = (
				_load_percentage_sample_functional_dependencies(
					source,
					target,
					plan,
					reference_data,
					batch_size=batch_size,
				)
			)
		except Exception as exc:
			frappe.db.rollback()
			report["issues"].append(f"Functional dependency closure: {exc}")

	if not report["issues"]:
		try:
			report["dependency_closure"] = _close_percentage_sample_dependencies(
				source,
				target,
				plan,
				reference_data,
				batch_size=batch_size,
			)
		except Exception as exc:
			frappe.db.rollback()
			report["issues"].append(f"Dependency closure: {exc}")

	if not report["issues"]:
		try:
			report["configuration_dependencies"] = (
				_load_percentage_sample_configuration_dependencies(
					source,
					target,
					plan,
					reference_data,
					batch_size=batch_size,
				)
			)
		except Exception as exc:
			frappe.db.rollback()
			report["issues"].append(f"Configuration dependencies: {exc}")

	if not report["issues"]:
		try:
			report["item_attribute_value_dependencies"] = (
				_ensure_standard_item_attribute_value_pairs()
			)
		except Exception as exc:
			frappe.db.rollback()
			report["issues"].append(f"Item attribute value dependencies: {exc}")

	if not report["issues"]:
		try:
			report["business_configuration"] = (
				_finalize_percentage_business_configuration()
			)
		except Exception as exc:
			frappe.db.rollback()
			report["issues"].append(f"Business configuration: {exc}")

	if not report["issues"]:
		try:
			report["series"] = _run_series(source, dry_run=False)
		except Exception as exc:
			frappe.db.rollback()
			report["issues"].append(f"Naming series: {exc}")

	if not report["issues"]:
		source_broken_links = _source_broken_link_manifest(plan, source)
		report["link_integrity"] = _verify_link_integrity(
			plan, source_broken_links
		)
		if report["link_integrity"]["failures"]:
			report["issues"].extend(report["link_integrity"]["failures"])

	if not report["issues"]:
		report["target_invariants"] = _verify_percentage_target_invariants(plan)
		if report["target_invariants"]["failures"]:
			report["issues"].extend(report["target_invariants"]["failures"])

	report["totals"] = dict(totals)
	report["failed_doctypes"] = sum(
		1 for row in report["doctypes"] if row["status"] == "Failed"
	)
	report["status"] = "Pass" if not report["issues"] else "Failed"
	_mark_sample_complete(migration_name, report)
	return report


def _finalize_percentage_business_configuration() -> dict[str, Any]:
	"""Apply configuration that could not exist before source masters were loaded.

	The app-install hook runs on a genuinely empty target and therefore cannot
	configure Essdee's Size/Stage Production Order contract yet.  A query-only
	migration loads those masters without document hooks, so this post-load
	boundary must rerun the idempotent initializer before link and form audits.
	"""
	from essdee_yrp.sd_yrp_sync import validate_yrp_settings_for_production_order
	from essdee_yrp.setup import ensure_yrp_production_order_settings

	changed = ensure_yrp_production_order_settings()
	validate_yrp_settings_for_production_order()
	frappe.db.commit()
	return {
		"status": "Pass",
		"production_order_settings": "Configured",
		"changed": bool(changed),
	}


def _load_percentage_sample_configuration_dependencies(
	source,
	target,
	plan,
	reference_data,
	*,
	batch_size,
) -> dict[str, Any]:
	"""Load exact source masters required by post-load Essdee configuration.

	Every reviewed ``attribute_value_link_to_data`` conversion intentionally
	removes the physical Link in F16.  The generic Link closure therefore cannot
	infer those source masters from the transformed target rows.  A percentage
	rehearsal must explicitly load every value used by any such field, plus the
	Size/Stage/Pack configuration contract, so opening and exercising a sampled
	document behaves like the full migration.
	"""
	transformed_attribute_values = _transformed_attribute_value_names(plan)
	required = {
		"Item Attribute": {"Size", "Stage"},
		"Item Attribute Value": {"Pack", *transformed_attribute_values},
	}
	result = {"status": "Pass", "required": 0, "already_present": 0, "loaded": 0}
	for source_doctype, names in required.items():
		if source_doctype not in plan.specs:
			raise MigrationError(
				f"Migration plan is missing configuration dependency {source_doctype}"
			)
		target_doctype = str(plan.specs[source_doctype].target)
		existing = target.existing_names(target_doctype, sorted(names))
		missing = names - existing
		result["required"] += len(names)
		result["already_present"] += len(existing)
		for chunk in _chunks(sorted(missing), batch_size):
			documents = []
			for source_document in source.iter_documents(
				source_doctype, batch_size=batch_size, names=chunk
			):
				document = transform_document(source_document, plan)
				_resolve_and_validate_required_target_values(
					document, plan, reference_data=reference_data
				)
				_strip_password_values(document)
				documents.append(document)
			if len(documents) != len(chunk):
				raise MigrationError(
					f"Source returned {len(documents)} of {len(chunk)} exact "
					f"{source_doctype} configuration dependencies"
				)
			target.upsert_batch(target_doctype, documents)
			verification = _verify_documents_sql(documents, plan)
			if verification["issues"]:
				raise MigrationError("; ".join(verification["issues"][:20]))
			result["loaded"] += len(documents)
			frappe.db.commit()
	return result


def _transformed_attribute_value_names(plan) -> set[str]:
	"""Collect every populated target value converted from a legacy IAV Link."""

	values: set[str] = set()
	seen_fields: set[tuple[str, str]] = set()
	for spec in plan.specs.values():
		for source_fieldname, transformer in spec.value_transformers.items():
			if transformer != "attribute_value_link_to_data":
				continue
			target_doctype = str(spec.target)
			target_fieldname = str(
				spec.field_map.get(source_fieldname, source_fieldname)
			)
			identity = (target_doctype, target_fieldname)
			if identity in seen_fields:
				continue
			seen_fields.add(identity)
			meta = frappe.get_meta(target_doctype)
			if meta.issingle:
				value = frappe.db.get_single_value(
					target_doctype, target_fieldname, cache=False
				)
				if value not in (None, ""):
					values.add(str(value))
				continue
			if not frappe.db.table_exists(target_doctype):
				continue
			if target_fieldname not in frappe.db.get_table_columns(target_doctype):
				continue
			rows = frappe.db.sql(
				f"SELECT DISTINCT {_quote_identifier(target_fieldname)} "
				f"FROM {_quote_identifier('tab' + target_doctype)} "
				f"WHERE COALESCE({_quote_identifier(target_fieldname)}, '')<>''"
			)
			values.update(str(row[0]) for row in rows)
	return values


def _verify_percentage_target_invariants(plan) -> dict[str, Any]:
	"""Exercise target-side derived state and one real onload per parent type.

	Source/target scalar equality cannot prove that a commonized ERPNext document
	is usable.  This gate catches target-only invariants (for example Purchase
	Order totals) and controller/onload failures caused by an incomplete linked
	graph (the failure mode that previously left the Vue item editor empty).
	"""

	failures: list[str] = []
	po = _verify_percentage_purchase_orders()
	failures.extend(po["failures"])
	opened = []
	for doctype in sorted({str(spec.target) for spec in plan.specs.values()}):
		meta = frappe.get_meta(doctype)
		if meta.istable:
			continue
		name = doctype if meta.issingle else frappe.db.get_value(doctype, {}, "name")
		if not name:
			continue
		try:
			document = (
				frappe.get_single(doctype)
				if meta.issingle
				else frappe.get_doc(doctype, name)
			)
			document.run_method("onload")
			opened.append(f"{doctype}:{name}")
		except Exception as exc:
			failures.append(f"Onload failed for {doctype} {name}: {exc}")
			if len(failures) >= 100:
				break
	return {
		"status": "Pass" if not failures else "Failed",
		"purchase_orders": po,
		"opened_parent_doctypes": len(opened),
		"opened_samples": opened,
		"failures": failures,
	}


def _verify_percentage_purchase_orders() -> dict[str, Any]:
	"""Verify every migrated YRP-managed standard Purchase Order by SQL."""

	if not frappe.db.table_exists("Purchase Order"):
		return {"checked": 0, "failures": ["Purchase Order target table is missing"]}
	rows = frappe.db.sql(
		"""
		SELECT
			po.name,
			COUNT(item.name) AS item_rows,
			COALESCE(po.total_qty, 0), COALESCE(SUM(item.qty), 0),
			COALESCE(po.total_stock_qty, 0), COALESCE(SUM(item.stock_qty), 0),
			COALESCE(po.total, 0), COALESCE(SUM(item.amount), 0),
			COALESCE(po.total_discount, 0), COALESCE(SUM(item.discount_amount), 0),
			COALESCE(po.total_tax, 0), COALESCE(SUM(item.tax_amount), 0),
			COALESCE(po.grand_total, 0), COALESCE(SUM(item.total_amount), 0),
			COALESCE(po.per_received, 0),
			CASE WHEN COALESCE(SUM(item.qty), 0)=0 THEN 0
				ELSE 100 * COALESCE(SUM(item.received_qty), 0) / SUM(item.qty) END,
			po.yrp_fulfillment_status, po.status
		FROM `tabPurchase Order` po
		LEFT JOIN `tabPurchase Order Item` item
			ON item.parent=po.name
			AND item.parenttype='Purchase Order'
			AND item.parentfield='items'
		WHERE COALESCE(po.is_yrp_managed, 0)=1
		GROUP BY po.name
		"""
	)
	failures = []
	for row in rows:
		(
			name,
			item_rows,
			total_qty,
			item_qty,
			total_stock_qty,
			item_stock_qty,
			total,
			item_total,
			total_discount,
			item_discount,
			total_tax,
			item_tax,
			grand_total,
			item_grand_total,
			per_received,
			item_per_received,
			fulfilment_status,
			status,
		) = row
		mismatches = []
		if not int(item_rows or 0):
			mismatches.append("no items")
		for label, actual, expected in (
			("total_qty", total_qty, item_qty),
			("total_stock_qty", total_stock_qty, item_stock_qty),
			("total", total, item_total),
			("total_discount", total_discount, item_discount),
			("total_tax", total_tax, item_tax),
			("grand_total", grand_total, item_grand_total),
			("per_received", per_received, item_per_received),
		):
			if abs(Decimal(str(actual or 0)) - Decimal(str(expected or 0))) > Decimal(
				"0.000001"
			):
				mismatches.append(label)
		expected_status = {
			"Ordered": "To Receive",
			"Partially Received": "To Receive",
			"Received": "Completed",
		}.get(str(fulfilment_status or ""), str(fulfilment_status or ""))
		if str(status or "") != expected_status:
			mismatches.append("status")
		if mismatches:
			failures.append(f"Purchase Order {name}: {', '.join(mismatches)}")
			if len(failures) >= 100:
				break
	return {
		"status": "Pass" if not failures else "Failed",
		"checked": len(rows),
		"failures": failures,
	}


def _load_percentage_sample_functional_dependencies(
	source,
	target,
	plan,
	reference_data,
	*,
	batch_size,
) -> dict[str, Any]:
	"""Load non-Link rows required to exercise selected transaction forms."""

	edit_source = "Cut Bundle Edit"
	ledger_source = "Cut Bundle Movement Ledger"
	if edit_source not in plan.specs or ledger_source not in plan.specs:
		return {"status": "Pass", "required": 0, "already_present": 0, "loaded": 0}
	edit_target = str(plan.specs[edit_source].target)
	ledger_target = str(plan.specs[ledger_source].target)
	edit_names = set(frappe.get_all(edit_target, pluck="name"))
	if not edit_names:
		return {"status": "Pass", "required": 0, "already_present": 0, "loaded": 0}

	dependency_names = {
		str(row.get("name"))
		for row in source.iter_cut_bundle_edit_ledger_dependencies(edit_names)
		if row.get("source_doctype") == ledger_source and row.get("name")
	}
	existing = target.existing_names(ledger_target, sorted(dependency_names))
	missing = dependency_names - existing
	loaded = 0
	for chunk in _chunks(sorted(missing), batch_size):
		documents = []
		for source_document in source.iter_documents(
			ledger_source, batch_size=batch_size, names=chunk
		):
			document = transform_document(source_document, plan)
			_resolve_and_validate_required_target_values(
				document, plan, reference_data=reference_data
			)
			_strip_password_values(document)
			documents.append(document)
		if len(documents) != len(chunk):
			raise MigrationError(
				f"Source returned {len(documents)} of {len(chunk)} exact "
				"Cut Bundle Movement Ledger dependencies"
			)
		target.upsert_batch(ledger_target, documents)
		verification = _verify_documents_sql(documents, plan)
		if verification["issues"]:
			raise MigrationError("; ".join(verification["issues"][:20]))
		loaded += len(documents)
		frappe.db.commit()
	return {
		"status": "Pass",
		"required": len(dependency_names),
		"already_present": len(existing),
		"loaded": loaded,
	}


def _source_candidates_by_target(plan) -> dict[str, set[str]]:
	"""Map each physical target DocType to every source route that can own it."""

	reverse: dict[str, set[str]] = defaultdict(set)
	for source_doctype, spec in plan.specs.items():
		reverse[str(spec.target)].add(str(source_doctype))
		source_fields = {
			str(field.get("fieldname")): field
			for field in spec.source_schema.get("fields") or []
			if field.get("fieldname")
		}
		target_fields = {
			str(field.get("fieldname")): field
			for field in spec.target_schema.get("fields") or []
			if field.get("fieldname")
		}
		for source_fieldname, source_field in source_fields.items():
			if source_field.get("fieldtype") not in TABLE_FIELD_TYPES:
				continue
			source_child = source_field.get("options")
			target_fieldname = spec.field_map.get(source_fieldname, source_fieldname)
			target_child = spec.table_option_map.get(source_fieldname) or (
				(target_fields.get(target_fieldname) or {}).get("options")
			)
			if source_child and target_child:
				reverse[str(target_child)].add(str(source_child))
	# A migrated Supplier also materializes the same-named standard Warehouse.
	# Source warehouse references historically carry Supplier identities.
	reverse["Warehouse"].add("Supplier")
	return reverse


def _existing_names(doctype: str, names: set[str]) -> set[str]:
	if not names or not frappe.db.exists("DocType", doctype):
		return set()
	meta = frappe.get_meta(doctype)
	if meta.issingle:
		return {doctype} if doctype in names else set()
	if not frappe.db.table_exists(doctype):
		return set()
	found = set()
	for chunk in _chunks(sorted(names), 500):
		placeholders = ", ".join(["%s"] * len(chunk))
		found.update(
			str(row[0])
			for row in frappe.db.sql(
				f"SELECT `name` FROM {_quote_identifier('tab' + doctype)} "
				f"WHERE `name` IN ({placeholders})",
				chunk,
			)
		)
	return found


def _collect_missing_link_identities(plan) -> dict[str, set[str]]:
	"""Return distinct missing target identities across every migrated Link."""

	missing: dict[str, set[str]] = defaultdict(set)
	parent_targets = tuple(
		sorted(
			{
				str(spec.target)
				for spec in plan.specs.values()
				if not spec.is_child
			}
		)
	)
	for doctype in _migration_physical_target_doctypes(plan):
		if doctype not in plan.target_schemas:
			raise MigrationError(f"Missing migration target schema for {doctype}")
		schema = plan.target_schemas[doctype]
		meta = frappe.get_meta(doctype)
		# Single DocTypes live in tabSingles and intentionally have no physical
		# ``tab<DocType>`` table.  Checking table_exists() before issingle skipped
		# every migrated Single during dependency closure, even though the final
		# link audit correctly inspected it.  That allowed migrated setting values
		# such as default Processes/Print Formats to fail only after all 29 closure
		# rounds had finished.  Singles must participate in the same closure scan;
		# only an absent non-Single table is outside the physical migration graph.
		if not meta.issingle and not frappe.db.table_exists(doctype):
			continue
		columns = set() if meta.issingle else set(frappe.db.get_table_columns(doctype))
		child_scope = (
			" AND source.parenttype IN %s" if meta.istable and parent_targets else ""
		)
		child_scope_params = (parent_targets,) if child_scope else ()
		for field in schema.get("fields") or []:
			fieldname = str(field.get("fieldname") or "")
			fieldtype = field.get("fieldtype")
			if not fieldname:
				continue
			if fieldtype == "Link" and field.get("options"):
				linked_doctype = str(field["options"])
				if not frappe.db.exists("DocType", linked_doctype):
					raise MigrationError(
						f"{doctype}.{fieldname} links to missing DocType {linked_doctype}"
					)
				if meta.issingle:
					# Migration writes Singles through SQL, and other setup/migration
					# code can repopulate the process-local value cache between writes.
					# Dependency closure must always inspect the committed row, not a
					# cached pre-migration default.
					value = frappe.db.get_single_value(
						doctype, fieldname, cache=False
					)
					if value and value not in _existing_names(
						linked_doctype, {str(value)}
					):
						missing[linked_doctype].add(str(value))
					continue
				if fieldname not in columns:
					continue
				linked_meta = frappe.get_meta(linked_doctype)
				if linked_meta.issingle:
					rows = frappe.db.sql(
						f"SELECT DISTINCT source.{_quote_identifier(fieldname)} "
						f"FROM {_quote_identifier('tab' + doctype)} source "
						f"WHERE COALESCE(source.{_quote_identifier(fieldname)}, '')<>'' "
						f"AND source.{_quote_identifier(fieldname)}<>%s{child_scope}",
						(linked_doctype, *child_scope_params),
					)
					missing[linked_doctype].update(str(row[0]) for row in rows)
					continue
				rows = frappe.db.sql(
					f"SELECT DISTINCT source.{_quote_identifier(fieldname)} "
					f"FROM {_quote_identifier('tab' + doctype)} source "
					f"LEFT JOIN {_quote_identifier('tab' + linked_doctype)} linked "
					f"ON linked.name=source.{_quote_identifier(fieldname)} "
					f"WHERE COALESCE(source.{_quote_identifier(fieldname)}, '')<>'' "
					f"AND linked.name IS NULL{child_scope}",
					child_scope_params,
				)
				missing[linked_doctype].update(str(row[0]) for row in rows)
			elif fieldtype == "Dynamic Link" and field.get("options"):
				controller = str(field["options"])
				if fieldname not in columns or controller not in columns:
					if not meta.issingle:
						continue
				if meta.issingle:
					linked_doctype = frappe.db.get_single_value(
						doctype, controller, cache=False
					)
					value = frappe.db.get_single_value(
						doctype, fieldname, cache=False
					)
					if value and (
						not linked_doctype
						or not frappe.db.exists("DocType", linked_doctype)
						or value not in _existing_names(
							str(linked_doctype), {str(value)}
						)
					):
						missing[str(linked_doctype or "<blank Dynamic Link>")].add(
							str(value)
						)
					continue
				rows = frappe.db.sql(
					f"SELECT DISTINCT {_quote_identifier(controller)}, "
					f"{_quote_identifier(fieldname)} "
					f"FROM {_quote_identifier('tab' + doctype)} source "
					f"WHERE COALESCE(source.{_quote_identifier(controller)}, '')<>'' "
					f"AND COALESCE(source.{_quote_identifier(fieldname)}, '')<>''"
					f"{child_scope}",
					child_scope_params,
				)
				by_doctype: dict[str, set[str]] = defaultdict(set)
				for linked_doctype, value in rows:
					by_doctype[str(linked_doctype)].add(str(value))
				for linked_doctype, values in by_doctype.items():
					if not frappe.db.exists("DocType", linked_doctype):
						raise MigrationError(
							f"{doctype}.{fieldname} selects missing DocType {linked_doctype}"
						)
					missing[linked_doctype].update(
						values - _existing_names(linked_doctype, values)
					)
	return {doctype: names for doctype, names in missing.items() if names}


def _close_percentage_sample_dependencies(
	source,
	target,
	plan,
	reference_data,
	*,
	batch_size,
) -> dict[str, Any]:
	"""Expand the percentage roots until every migrated Link is resolvable.

	The source graph is finite and every attempted identity is remembered.  A
	fixed round ceiling is therefore both unnecessary and incorrect: a valid
	historical graph can be deeper than the arbitrary limit even though every
	round is still loading new records.  Stop only at closure or when unresolved
	links remain without any unattempted source identity that could resolve them.
	"""

	reverse = _source_candidates_by_target(plan)
	audited_missing: dict[str, set[str]] = defaultdict(set)
	for row in _source_broken_link_manifest(plan, source):
		if row.get("target_link_doctype") and row.get("value"):
			audited_missing[str(row["target_link_doctype"])].add(str(row["value"]))
	attempted_parent_names: dict[str, set[str]] = defaultdict(set)
	attempted_external_names: dict[str, set[str]] = defaultdict(set)
	inspected_purchase_invoice_names: set[str] = set()
	total_loaded = defaultdict(int)
	rounds = []
	round_number = 0
	while True:
		round_number += 1
		missing = _collect_missing_link_identities(plan)
		# Try to resolve every missing identity first. A value that is invalid in
		# one source row can still be a valid identity supplied by another source
		# route which maps into the same commonized target DocType.
		actionable_missing = dict(missing)
		if not actionable_missing:
			return {
				"status": "Pass",
				"rounds": rounds,
				"loaded_parent_documents": dict(total_loaded),
				"audited_source_invalid_identities": sum(
					len(names) for names in missing.values()
				),
			}

		parent_names: dict[str, set[str]] = defaultdict(set)
		external_missing: dict[str, set[str]] = defaultdict(set)
		unrouted: dict[str, set[str]] = defaultdict(set)
		for target_doctype, target_names in actionable_missing.items():
			candidates = reverse.get(target_doctype) or set()
			if not candidates:
				if target_doctype in SUPPORTING_EXTERNAL_DOCTYPE_ORDER:
					external_missing[target_doctype].update(target_names)
				else:
					unrouted[target_doctype].update(target_names)
				continue
			resolved_target_names = set()
			for source_doctype in sorted(candidates):
				for identity in source.resolve_source_identities(
					source_doctype, target_names
				):
					resolved_target_names.add(str(identity["name"]))
					if identity.get("parent") and identity.get("parenttype"):
						parent_doctype = str(identity["parenttype"])
						if parent_doctype not in plan.parent_doctypes:
							unrouted[target_doctype].add(str(identity["name"]))
							continue
						parent_names[parent_doctype].add(str(identity["parent"]))
					else:
						parent_names[source_doctype].add(str(identity["name"]))
			unresolved = target_names - resolved_target_names
			# Only genuinely absent source identities may be retained for the final
			# exact owner/field audit. The final verifier—not this value-level set—
			# decides whether every use is one of the approved source exceptions.
			unapproved_unresolved = unresolved - audited_missing.get(
				target_doctype, set()
			)
			if unapproved_unresolved:
				unrouted[target_doctype].update(unapproved_unresolved)

		# Work Order invoice projection executes before the invoice itself is
		# written and reads every GRN selected in its child table.  Those GRN Links
		# are not visible to the generic target-side scan until after insertion, so
		# explicitly surface them as prerequisites and let the normal closure loop
		# load their own dependency graph before admitting the invoice.
		purchase_invoice_names = parent_names.get("Purchase Invoice") or set()
		uninspected_invoices = (
			purchase_invoice_names - inspected_purchase_invoice_names
		)
		if uninspected_invoices:
			required_grns = _purchase_invoice_grn_dependencies(
				source,
				uninspected_invoices,
				batch_size=batch_size,
			)
			inspected_purchase_invoice_names.update(uninspected_invoices)
			grn_target = plan.specs["Goods Received Note"].target
			missing_grns = required_grns - _existing_names(
				grn_target, required_grns
			)
			if missing_grns:
				parent_names["Goods Received Note"].update(missing_grns)

		# Exact source-invalid links are allowed only by the final audited manifest;
		# every other unresolved identity is a hard sample failure.
		if unrouted:
			summary = "; ".join(
				f"{doctype}: {len(names)} ({', '.join(sorted(names)[:5])})"
				for doctype, names in sorted(unrouted.items())
			)
			raise MigrationError(f"No source route for missing target Links: {summary}")

		new_parent_names = {
			doctype: names - attempted_parent_names[doctype]
			for doctype, names in parent_names.items()
			if names - attempted_parent_names[doctype]
		}
		new_external_missing = {
			doctype: names - attempted_external_names[doctype]
			for doctype, names in external_missing.items()
			if names - attempted_external_names[doctype]
		}
		if not new_parent_names and not new_external_missing:
			unaudited_remaining = {
				doctype: names - audited_missing.get(doctype, set())
				for doctype, names in actionable_missing.items()
				if names - audited_missing.get(doctype, set())
			}
			if not unaudited_remaining:
				return {
					"status": "Pass",
					"rounds": rounds,
					"loaded_parent_documents": dict(total_loaded),
					"audited_source_invalid_identities": sum(
						len(names) for names in actionable_missing.values()
					),
				}
			remaining = "; ".join(
				f"{doctype}: {len(names)} ({', '.join(sorted(names)[:5])})"
				for doctype, names in sorted(unaudited_remaining.items())
			)
			raise MigrationError(
				"Dependency closure made no progress with remaining missing Links: "
				+ remaining
			)

		loaded_this_round = defaultdict(int)
		if new_external_missing:
			for doctype, names in new_external_missing.items():
				attempted_external_names[doctype].update(names)
			loaded = _load_supporting_external_masters(
				target,
				source,
				new_external_missing,
				plan=plan,
				dry_run=False,
			)
			for doctype, count in loaded.items():
				loaded_this_round[doctype] += int(count)
			frappe.db.commit()

		ordered, deferred_purchase_invoices = _dependency_round_order(
			plan,
			new_parent_names,
			new_external_missing,
		)
		for source_doctype in ordered:
			names = new_parent_names.get(source_doctype) or set()
			if not names:
				continue
			attempted_parent_names[source_doctype].update(names)
			for chunk in _chunks(sorted(names), batch_size):
				documents = []
				for source_document in source.iter_documents(
					source_doctype, batch_size=batch_size, names=chunk
				):
					document = transform_document(source_document, plan)
					_resolve_and_validate_required_target_values(
						document, plan, reference_data=reference_data
					)
					_strip_password_values(document)
					documents.append(document)
				if source_doctype in {"Item", "Item Variant"}:
					documents = _prepare_item_migration_documents(
						source_doctype, documents
					)
				if source_doctype == "Purchase Invoice":
					documents = _prepare_purchase_invoice_migration_documents(documents)
				if len(documents) != len(chunk):
					raise MigrationError(
						f"Source returned {len(documents)} of {len(chunk)} exact "
						f"{source_doctype} dependencies"
					)
				target.upsert_batch(plan.specs[source_doctype].target, documents)
				verification = _verify_documents_sql(documents, plan)
				if verification["issues"]:
					raise MigrationError("; ".join(verification["issues"][:20]))
				loaded_this_round[source_doctype] += len(documents)
				frappe.db.commit()
		for doctype, count in loaded_this_round.items():
			total_loaded[doctype] += int(count)
		rounds.append(
			{
				"round": round_number,
				"missing_identities_before": sum(
					len(names) for names in actionable_missing.values()
				),
				"loaded": dict(loaded_this_round),
				"deferred_purchase_invoices": deferred_purchase_invoices,
			}
		)


def _purchase_invoice_grn_dependencies(source, invoice_names, *, batch_size):
	"""Return exact GRNs needed before projecting the given source invoices."""

	requested = {str(name) for name in invoice_names if name}
	returned = set()
	grns = set()
	for chunk in _chunks(sorted(requested), batch_size):
		for document in source.iter_documents(
			"Purchase Invoice", batch_size=batch_size, names=chunk
		):
			name = str(document.get("name") or "")
			if name:
				returned.add(name)
			for row in document.get("grn") or []:
				if row.get("grn"):
					grns.add(str(row["grn"]))
	missing = requested - returned
	if missing:
		raise MigrationError(
			"Source returned no Purchase Invoice dependency document for: "
			+ ", ".join(sorted(missing)[:20])
		)
	return grns


def _dependency_round_order(plan, new_parent_names, external_missing):
	"""Defer Purchase Invoice until newly introduced dependencies reach closure.

	Work Order invoice projection executes target business code while it rebuilds
	the hidden GRN valuation rows.  A closure round can discover the invoice and
	its Work Order/Process together; the Process's billing Item is only visible to
	the *next* missing-link scan.  Loading the invoice in that same round therefore
	races a valid source graph too early and falsely reports the billing Item as
	missing.  All ordinary parents are safe SQL projections, so load those first,
	rescan, and admit Purchase Invoice only when it is the sole pending source
	parent type for the round.
	"""

	ordered = [
		doctype
		for doctype in plan.parent_doctypes
		if doctype != "Purchase Invoice" and new_parent_names.get(doctype)
	]
	purchase_invoices = new_parent_names.get("Purchase Invoice") or set()
	deferred = bool(purchase_invoices and (ordered or external_missing))
	if purchase_invoices and not deferred:
		ordered.append("Purchase Invoice")
	return ordered, len(purchase_invoices) if deferred else 0


def _chunks(values, size):
	for offset in range(0, len(values), max(1, int(size))):
		yield values[offset : offset + max(1, int(size))]


def _percentage_limit(source_total: int, percentage: int) -> int:
	if int(source_total or 0) <= 0:
		return 0
	return max(1, math.ceil(int(source_total) * int(percentage) / 100))


def _write_percentage_batch(
	source_doctype: str,
	target_doctype: str,
	documents: list[dict[str, Any]],
	target: QueryOnlySampleTarget,
	plan,
	row: dict[str, Any],
) -> None:
	prepared = documents
	if source_doctype in {"Item", "Item Variant"}:
		prepared = _prepare_item_migration_documents(source_doctype, prepared)
	if source_doctype == "Purchase Invoice":
		prepared = _prepare_purchase_invoice_migration_documents(prepared)
	existing = target.existing_names(
		target_doctype, [str(document["name"]) for document in prepared]
	)
	target.upsert_batch(target_doctype, prepared)
	verification = _verify_documents_sql(prepared, plan)
	if verification["issues"]:
		raise MigrationError("; ".join(verification["issues"][:20]))
	frappe.db.commit()
	row["sampled_parents"] += len(prepared)
	row["sampled_children"] += verification["child_rows"]
	row["inserted_parents"] += len(prepared) - len(existing)
	row["updated_parents"] += len(existing)
	row["verified_field_values"] += verification["field_values"]


def _do_percentage_supporting_business_masters(
	source,
	target,
	plan,
	source_status,
	percentage,
	batch_size,
	report,
) -> None:
	names_by_doctype: dict[str, list[str]] = defaultdict(list)
	for row in source.iter_related_business_masters():
		doctype = str(row.get("doctype") or "")
		name = str(row.get("name") or "")
		if doctype not in {"Address", "Contact"} or not name:
			raise MigrationError("Invalid related business-master scope")
		names_by_doctype[doctype].append(name)
	doctype_map = {name: spec.target for name, spec in plan.specs.items()}
	status_counts = source_status.get("related_business_master_counts") or {}
	for doctype in ("Address", "Contact"):
		names = sorted(set(names_by_doctype.get(doctype) or []))
		source_total = int(status_counts.get(doctype) or len(names))
		requested = _percentage_limit(source_total, percentage)
		selected = names[:requested]
		row = {
			"source_doctype": doctype,
			"target_doctype": doctype,
			"source_total": source_total,
			"requested_parents": requested,
			"sampled_parents": 0,
			"sampled_children": 0,
			"verified_field_values": 0,
			"status": "Pass",
			"issues": [],
		}
		try:
			frappe.db.savepoint(f"mrp_supporting_sample_{doctype.lower()}")
			for offset in range(0, len(selected), batch_size):
				documents = [
					_transform_supporting_document(document, doctype, doctype_map)
					for document in source.iter_supporting_documents(
						doctype, selected[offset : offset + batch_size]
					)
				]
				for document in documents:
					_strip_password_values(document)
				target.upsert_batch(doctype, documents)
				verification = _verify_documents_sql(documents, plan)
				if verification["issues"]:
					raise MigrationError("; ".join(verification["issues"][:20]))
				row["sampled_parents"] += len(documents)
				row["sampled_children"] += verification["child_rows"]
				row["verified_field_values"] += verification["field_values"]
			if row["sampled_parents"] != requested:
				raise MigrationError("Source returned an incomplete supporting sample")
			frappe.db.commit()
		except Exception as exc:
			frappe.db.rollback(save_point=f"mrp_supporting_sample_{doctype.lower()}")
			row["status"] = "Failed"
			row["issues"].append(str(exc))
			report["issues"].append(f"{doctype}: {exc}")
		report["supporting_business_masters"].append(row)


def _do_percentage_approved_frappe_data(
	source,
	target,
	plan,
	source_status,
	percentage,
	batch_size,
	report,
) -> None:
	counts = (
		(source_status.get("approved_frappe_data") or {}).get("counts") or {}
	)
	limits = {
		doctype: _percentage_limit(int(count or 0), percentage)
		for doctype, count in counts.items()
	}
	seen = defaultdict(int)
	rows_by_doctype: dict[str, dict[str, Any]] = {}
	default_value_documents: list[dict[str, Any]] = []
	user_unique_value_reconciliation = {
		"status": "Reconciled",
		"source_users": 0,
		"conflicting_optional_values": 0,
		"cleared_source_aliases": 0,
		"preserved_target_users": 0,
		"by_field": {},
	}
	batch: list[dict[str, Any]] = []
	batch_doctype = None

	def flush() -> None:
		nonlocal batch
		if not batch:
			return
		row = rows_by_doctype[str(batch[0]["doctype"])]
		for document in batch:
			_assert_approved_frappe_child_identities(document)
		target.upsert_batch(str(batch[0]["doctype"]), batch)
		verification = _verify_documents_sql(batch, plan)
		if verification["issues"]:
			raise MigrationError("; ".join(verification["issues"][:20]))
		row["sampled_parents"] += len(batch)
		row["sampled_children"] += verification["child_rows"]
		row["verified_field_values"] += verification["field_values"]
		batch = []

	frappe.db.savepoint("mrp_approved_frappe_sample")
	try:
		for source_document in source.iter_approved_frappe_documents():
			doctype = str(source_document.get("doctype") or "")
			if doctype not in limits or seen[doctype] >= limits[doctype]:
				continue
			seen[doctype] += 1
			row = rows_by_doctype.setdefault(
				doctype,
				{
					"source_doctype": doctype,
					"target_doctype": doctype,
					"source_total": int(counts[doctype]),
					"requested_parents": limits[doctype],
					"sampled_parents": 0,
					"sampled_children": 0,
					"verified_field_values": 0,
					"skipped_unavailable_targets": 0,
					"status": "Pass",
					"issues": [],
				},
			)
			document = _prepare_approved_frappe_document(source_document, plan)
			if document is None:
				row["skipped_unavailable_targets"] += 1
				continue
			_strip_password_values(document)
			unique_result = _reconcile_approved_user_unique_values(
				[document], dry_run=False
			)
			user_unique_value_reconciliation["source_users"] += unique_result[
				"source_users"
			]
			user_unique_value_reconciliation[
				"conflicting_optional_values"
			] += unique_result["conflicting_optional_values"]
			user_unique_value_reconciliation["cleared_source_aliases"] += (
				unique_result["cleared_source_aliases"]
			)
			user_unique_value_reconciliation["preserved_target_users"] += (
				unique_result["preserved_target_users"]
			)
			for fieldname, count in unique_result["by_field"].items():
				by_field = user_unique_value_reconciliation["by_field"]
				by_field[fieldname] = by_field.get(fieldname, 0) + count
			if doctype == "DefaultValue":
				default_value_documents.append(document)
			if batch and (batch_doctype != doctype or len(batch) >= batch_size):
				flush()
			batch_doctype = doctype
			batch.append(document)
		flush()
		report["approved_frappe_default_value_reconciliation"] = (
			_reconcile_approved_default_values(
				default_value_documents,
				dry_run=False,
			)
		)
		report["approved_frappe_user_unique_value_reconciliation"] = (
			user_unique_value_reconciliation
		)
		frappe.db.commit()
		frappe.clear_cache()
	except Exception as exc:
		frappe.db.rollback(save_point="mrp_approved_frappe_sample")
		report["issues"].append(f"Approved Frappe data: {exc}")
		if batch_doctype and batch_doctype in rows_by_doctype:
			rows_by_doctype[batch_doctype]["status"] = "Failed"
			rows_by_doctype[batch_doctype]["issues"].append(str(exc))
	for doctype, source_total in counts.items():
		row = rows_by_doctype.setdefault(
			doctype,
			{
				"source_doctype": doctype,
				"target_doctype": doctype,
				"source_total": int(source_total),
				"requested_parents": limits[doctype],
				"sampled_parents": 0,
				"sampled_children": 0,
				"verified_field_values": 0,
				"skipped_unavailable_targets": 0,
				"status": "Pass",
				"issues": [],
			},
		)
		if seen[doctype] != limits[doctype]:
			row["status"] = "Failed"
			message = f"Source returned {seen[doctype]} of {limits[doctype]} requested rows"
			row["issues"].append(message)
			report["issues"].append(f"{doctype}: {message}")
	report["approved_frappe_data"] = [
		rows_by_doctype[doctype] for doctype in counts
	]


def _strip_password_values(document: dict[str, Any]) -> int:
	passwords = document.pop("__migration_passwords", {}) or {}
	meta = frappe.get_meta(str(document["doctype"]))
	password_fieldnames = {
		field.fieldname
		for field in meta.fields
		if field.fieldname and field.fieldtype == "Password"
	}
	table_fieldnames = {
		field.fieldname
		for field in meta.fields
		if field.fieldname and field.fieldtype in TABLE_FIELD_TYPES
	}
	count = len(passwords)
	for fieldname in password_fieldnames:
		if document.pop(fieldname, None) not in (None, "") and fieldname not in passwords:
			count += 1
	# A JSON field may legitimately contain source-shaped dictionaries whose
	# ``doctype`` does not exist on the target. Only actual child-table fields
	# participate in recursive password stripping.
	for fieldname in table_fieldnames:
		value = document.get(fieldname)
		if isinstance(value, list):
			for child in value:
				if isinstance(child, dict) and child.get("doctype"):
					count += _strip_password_values(child)
	return count


def _verify_documents_sql(documents, plan) -> dict[str, Any]:
	result = {
		"field_values": 0,
		"child_rows": 0,
		"issues": [],
		"_numeric_scales": {},
	}
	for document in documents:
		_verify_document_sql(document, plan, result)
	result.pop("_numeric_scales", None)
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
		actual_rows = frappe.db.sql(
			"SELECT `field`, `value` FROM `tabSingles` WHERE `doctype`=%s",
			(doctype,),
		)
		actual = dict(actual_rows)
		if len(actual_rows) != len(actual):
			duplicate_fields = sorted(
				fieldname
				for fieldname in actual
				if sum(1 for row in actual_rows if row[0] == fieldname) > 1
			)
			result["issues"].append(
				f"{doctype} has duplicate Single values: "
				+ ", ".join(duplicate_fields[:20])
			)
	else:
		columns = set(frappe.db.get_table_columns(doctype))
		numeric_scales_by_doctype = result["_numeric_scales"]
		if doctype not in numeric_scales_by_doctype:
			numeric_scales_by_doctype[doctype] = {
				str(row["column_name"]): int(row["numeric_scale"])
				for row in frappe.db.sql(
					"SELECT `column_name`, `numeric_scale` "
					"FROM `information_schema`.`columns` "
					"WHERE `table_schema`=DATABASE() AND `table_name`=%s "
					"AND `numeric_scale` IS NOT NULL",
					("tab" + doctype,),
					as_dict=True,
				)
			}
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
		numeric_scale = (
			result["_numeric_scales"].get(doctype, {}).get(fieldname)
			if not schema.get("issingle")
			else None
		)
		if not _same_db_value(
			expected_value,
			actual[fieldname],
			fieldtype,
			numeric_scale=numeric_scale,
		):
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


def _same_db_value(expected, actual, fieldtype, *, numeric_scale=None) -> bool:
	expected = _db_value(expected)
	if expected is None or actual is None:
		return expected is None and actual is None
	if fieldtype in NUMERIC_FIELD_TYPES:
		try:
			expected_decimal = Decimal(str(expected or 0))
			actual_decimal = Decimal(str(actual or 0))
			if numeric_scale is not None:
				expected_decimal = expected_decimal.quantize(
					Decimal(1).scaleb(-int(numeric_scale)),
					rounding=ROUND_HALF_UP,
				)
			return expected_decimal == actual_decimal
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


def _mark_percentage_sample_started(migration_name: str, requested_total: int) -> None:
	frappe.db.sql(
		"""
		UPDATE `tabSD YRP MRP Data Migration`
		SET `status`='Running', `last_action`='Sample', `last_started_on`=%s,
			`last_completed_on`=NULL, `total_source_records`=%s,
			`processed_records`=0, `skipped_records`=0, `failed_records`=0,
			`error_log`=NULL
		WHERE `name`=%s
		""",
		(now_datetime(), int(requested_total), migration_name),
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
