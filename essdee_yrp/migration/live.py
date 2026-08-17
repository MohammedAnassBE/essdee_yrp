"""Live, resumable Production API migration runner.

The source is read through a fixed Frappe-15 subprocess bridge.  Target writes
are DB-level batched upserts so historical documents retain their source state
without firing incomplete F16 workflow logic.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import frappe
from frappe.model import no_value_fields
from frappe.utils import get_datetime, now_datetime
from frappe.utils.password import set_encrypted_password

from essdee_yrp.migration.engine import MigrationError, MigrationPlan, transform_document
from essdee_yrp.migration.planner import SOURCE_SITE, TARGET_SITE, build_schema_analysis
from essdee_yrp.migration.transformers import DEFAULT_RECEIVED_TYPE


F15_BENCH = Path("/home/anas/frappe-15")
F15_PYTHON = F15_BENCH / "env" / "bin" / "python"
SOURCE_BRIDGE = (
	Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"
)
DEFAULT_BATCH_SIZE = 250
MAX_SQL_PARAMETERS = 20_000
PROGRESS_UPDATE_INTERVAL = 10_000
RUNNING_STATUSES = {"Queued", "Running", "Analysing"}
TABLE_FIELD_TYPES = {"Table", "Table MultiSelect"}
NO_COLUMN_FIELD_TYPES = set(no_value_fields) - TABLE_FIELD_TYPES
SUPPORTING_BILL_RECEIVED_VIA = ("HO", "Post", "Email", "Warehouse", "Others")
SUPPORTING_EXTERNAL_DOCTYPE_ORDER = (
	"Role",
	"User",
	"Address",
	"Letter Head",
	"Email Account",
	"Print Format",
)
LEGACY_REQUIRED_FIELD_CUTOFFS = {
	# Supplier was optional until the Production API change deployed on
	# 2025-11-20. Existing rows are historical rates, not malformed new data.
	("Process Cost", "supplier"): get_datetime("2025-11-21 00:00:00"),
	# Lot was introduced as optional on 2025-11-04 and made mandatory on
	# 2026-02-06. Preserve the earlier global/supplier-level rate records.
	("Process Cost", "lot"): get_datetime("2026-02-07 00:00:00"),
	# F16 added the mandatory operational header dimension on 2026-08-12.
	# Earlier Production API POs can legitimately span several per-row Lots.
	("Purchase Order", "lot"): get_datetime("2026-08-12 00:00:00"),
	# The source GRN header Lot was optional and, for multi-Lot Purchase Orders,
	# intentionally blank while every stock row retained its own Lot. F16 made
	# the operational header dimension mandatory only for new documents.
	("Goods Received Note", "lot"): get_datetime("2026-08-12 00:00:00"),
	# This field was added on 2025-07-08. The remaining unresolved pre-field
	# records end on 2025-07-16; later movements always carry the warehouse.
	("Cut Panel Movement", "from_warehouse"): get_datetime("2025-07-17 00:00:00"),
}


class F15SourceBridge:
	def schemas(self) -> dict[str, dict[str, Any]]:
		schemas = {}
		for row in self._run(["schemas"]):
			if row.get("kind") != "schema" or not isinstance(row.get("schema"), dict):
				raise MigrationError("F15 source bridge returned an invalid schema payload")
			schema = row["schema"]
			name = schema.get("name")
			if not name or name in schemas:
				raise MigrationError("F15 source bridge returned duplicate/unnamed metadata")
			schemas[str(name)] = schema
		if not schemas:
			raise MigrationError("F15 source bridge returned no schemas")
		return schemas

	def status(self) -> dict[str, Any]:
		lines = list(self._run(["status"]))
		if len(lines) != 1:
			raise MigrationError("F15 source bridge returned an invalid status payload")
		return lines[0]

	def iter_documents(
		self,
		doctype: str,
		*,
		start_after: str | None = None,
		batch_size: int = DEFAULT_BATCH_SIZE,
		limit: int | None = None,
	) -> Iterable[dict[str, Any]]:
		args = ["export", "--doctype", doctype, "--batch-size", str(batch_size)]
		if start_after:
			args.extend(["--start-after", start_after])
		if limit is not None:
			args.extend(["--limit", str(max(0, int(limit)))])
		yield from self._run(args)

	def reference_data(self) -> dict[str, Any]:
		data = {
			"variant_to_item": {},
			"item_defaults": {},
			"item_groups": {},
			"cut_panel_from_warehouse": {},
		}
		conflicts = []
		for row in self._run(["reference-data"]):
			kind = row.get("kind")
			name = row.get("name")
			if kind == "item":
				data["item_defaults"][name] = row.get("default_uom")
				data["item_groups"][name] = row.get("item_group")
			elif kind == "item_variant":
				data["variant_to_item"][name] = row.get("item")
			elif kind == "cut_panel_from_warehouse":
				if len(row.get("candidates") or []) > 1:
					conflicts.append(row)
				elif row.get("warehouse"):
					data["cut_panel_from_warehouse"][name] = row["warehouse"]
		if conflicts:
			raise MigrationError(
				"Conflicting Cut Panel Movement warehouse references: "
				+ "; ".join(
					f"{row['name']}={row['candidates']}" for row in conflicts[:20]
				)
			)
		return data

	def file_status(self, names: Iterable[str] | None = None) -> dict[str, Any]:
		args = ["file-status"]
		if names is not None:
			args.extend(["--names-json", json.dumps(sorted(set(names)))])
		lines = list(self._run(args))
		if len(lines) != 1:
			raise MigrationError("F15 source bridge returned invalid file status")
		return lines[0]

	def iter_files(
		self,
		*,
		start_after: str | None = None,
		metadata_only: bool = False,
		names: Iterable[str] | None = None,
		allow_missing: bool = False,
	) -> Iterable[dict[str, Any]]:
		args = ["files"]
		if start_after:
			args.extend(["--start-after", start_after])
		if metadata_only:
			args.append("--metadata-only")
		if names is not None:
			args.extend(["--names-json", json.dumps(sorted(set(names)))])
		if allow_missing:
			args.append("--allow-missing")
		yield from self._run(args)

	def stock_summary(self) -> dict[str, Any]:
		lines = list(self._run(["stock-summary"]))
		if len(lines) != 1:
			raise MigrationError("F15 source bridge returned invalid stock summary")
		return lines[0]

	def iter_series(self) -> Iterable[dict[str, Any]]:
		yield from self._run(["series"])

	def iter_external_references(self) -> Iterable[dict[str, Any]]:
		yield from self._run(["external-references"])

	def iter_supporting_documents(
		self, doctype: str, names: Iterable[str]
	) -> Iterable[dict[str, Any]]:
		names = list(names)
		if not names:
			return
		yield from self._run(
			[
				"supporting-documents",
				"--doctype",
				doctype,
				"--names-json",
				json.dumps(names, separators=(",", ":")),
			]
		)

	def _run(self, args: list[str]) -> Iterable[dict[str, Any]]:
		if not F15_PYTHON.is_file() or not SOURCE_BRIDGE.is_file():
			raise MigrationError("The fixed F15 source bridge is not installed")
		with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr:
			process = subprocess.Popen(
				[str(F15_PYTHON), str(SOURCE_BRIDGE), *args],
				cwd=F15_BENCH,
				stdout=subprocess.PIPE,
				stderr=stderr,
				text=True,
				bufsize=1,
			)
			assert process.stdout is not None
			try:
				for line in process.stdout:
					line = line.strip()
					if line:
						yield json.loads(line)
			finally:
				process.stdout.close()
			return_code = process.wait()
			if return_code:
				stderr.seek(0)
				message = stderr.read().strip()
				raise MigrationError(
					f"F15 source bridge failed with exit {return_code}: {message[-4000:]}"
				)


class FrappeBulkTarget:
	def upsert_batch(self, target_doctype: str, documents: list[dict[str, Any]]) -> None:
		if not documents:
			return
		meta = frappe.get_meta(target_doctype)
		if meta.issingle:
			for document in documents:
				self._upsert_single(meta, document)
			self._replace_child_tables(meta, documents)
			return

		table_fields = {field.fieldname: field for field in meta.get_table_fields()}
		parent_rows = []
		passwords = []
		for document in documents:
			row = {
				key: value
				for key, value in document.items()
				if key not in table_fields and key not in {"doctype", "__migration_passwords"}
			}
			parent_rows.append(row)
			for fieldname, value in (document.get("__migration_passwords") or {}).items():
				passwords.append((document["name"], fieldname, value))

		self._bulk_upsert(target_doctype, parent_rows)
		self._replace_child_tables(meta, documents)

		for name, fieldname, value in passwords:
			set_encrypted_password(target_doctype, name, value, fieldname=fieldname)
		if target_doctype == "Supplier":
			self._upsert_supplier_warehouses(documents)

	def _replace_child_tables(self, meta, documents: list[dict[str, Any]]) -> None:
		target_doctype = meta.name
		table_fields = {field.fieldname: field for field in meta.get_table_fields()}
		for fieldname, table_field in table_fields.items():
			parents_with_field = [doc for doc in documents if fieldname in doc]
			if not parents_with_field:
				continue
			parent_names = [doc["name"] for doc in parents_with_field]
			for names in _chunks(parent_names, 500):
				frappe.db.delete(
					table_field.options,
					{
						"parenttype": target_doctype,
						"parentfield": fieldname,
						"parent": ["in", names],
					},
				)
			child_rows = []
			for document in parents_with_field:
				for idx, child in enumerate(document.get(fieldname) or [], start=1):
					if child.get("doctype") != table_field.options:
						raise MigrationError(
							f"{target_doctype}.{fieldname} expected {table_field.options}, "
							f"received {child.get('doctype')}"
						)
					row = {
						key: value
						for key, value in child.items()
						if key not in {"doctype", "__migration_passwords"}
					}
					row.update(
						{
							"name": row.get("name") or frappe.generate_hash(length=10),
							"parent": document["name"],
							"parenttype": target_doctype,
							"parentfield": fieldname,
							"idx": idx,
						}
					)
					child_rows.append(row)
			self._bulk_upsert(table_field.options, child_rows)

	def _upsert_single(self, meta, document: Mapping[str, Any]) -> None:
		skip = {
			"doctype",
			"name",
			"creation",
			"modified",
			"owner",
			"modified_by",
			"docstatus",
			"idx",
			"__migration_passwords",
		}
		valid_fields = {
			field.fieldname
			for field in meta.fields
			if field.fieldname and field.fieldtype not in NO_COLUMN_FIELD_TYPES | TABLE_FIELD_TYPES
		}
		for fieldname, value in document.items():
			if fieldname in skip or fieldname not in valid_fields:
				continue
			frappe.db.set_single_value(meta.name, fieldname, _db_value(value))
		for fieldname, value in (document.get("__migration_passwords") or {}).items():
			if fieldname in valid_fields:
				set_encrypted_password(meta.name, meta.name, value, fieldname=fieldname)
		frappe.clear_document_cache(meta.name, meta.name)

	def _bulk_upsert(self, doctype: str, rows: list[dict[str, Any]]) -> None:
		if not rows:
			return
		columns = set(frappe.db.get_table_columns(doctype))
		fields = [
			fieldname
			for fieldname in dict.fromkeys(
				["name", *[key for row in rows for key in row]]
			)
			if fieldname in columns
		]
		if "name" not in fields:
			raise MigrationError(f"{doctype} has no physical name column")
		chunk_size = max(1, min(len(rows), MAX_SQL_PARAMETERS // max(len(fields), 1)))
		quoted_table = _quote_identifier(f"tab{doctype}")
		quoted_fields = ", ".join(_quote_identifier(fieldname) for fieldname in fields)
		updates = ", ".join(
			f"{_quote_identifier(fieldname)}=VALUES({_quote_identifier(fieldname)})"
			for fieldname in fields
			if fieldname != "name"
		) or "`name`=VALUES(`name`)"
		for chunk in _chunks(rows, chunk_size):
			placeholders = ", ".join(
				"(" + ", ".join(["%s"] * len(fields)) + ")" for _row in chunk
			)
			values = [
				_db_value(row.get(fieldname))
				for row in chunk
				for fieldname in fields
			]
			frappe.db.sql(
				f"INSERT INTO {quoted_table} ({quoted_fields}) VALUES {placeholders} "
				f"ON DUPLICATE KEY UPDATE {updates}",
				values,
			)

	def _upsert_supplier_warehouses(self, suppliers: list[dict[str, Any]]) -> None:
		rows = []
		for supplier in suppliers:
			name = supplier.get("name")
			if not name:
				continue
			rows.append(
				{
					"name": name,
					"name1": name,
					"supplier": name,
					"disabled": supplier.get("disabled") or 0,
					"owner": supplier.get("owner") or "Administrator",
					"creation": supplier.get("creation"),
					"modified": supplier.get("modified"),
					"modified_by": supplier.get("modified_by") or "Administrator",
					"docstatus": 0,
				}
			)
		self._bulk_upsert("Warehouse", rows)

	def upsert_file(
		self,
		row: Mapping[str, Any],
		plan: MigrationPlan,
	) -> dict[str, Any]:
		"""Create one historical attachment through Frappe's File lifecycle."""

		source_doctype = str(row.get("attached_to_doctype") or "")
		if source_doctype not in plan.specs:
			raise MigrationError(
				f"File {row.get('name')} uses unmapped DocType {source_doctype!r}"
			)
		spec = plan.specs[source_doctype]
		target_doctype = spec.target
		target_name = row.get("attached_to_name")
		if not target_name or not frappe.db.exists(target_doctype, target_name):
			raise MigrationError(
				f"File {row.get('name')} target {target_doctype} {target_name!r} does not exist"
			)
		source_field = row.get("attached_to_field")
		target_field = spec.field_map.get(source_field, source_field) if source_field else None

		existing_name = row.get("name")
		if frappe.db.exists("File", existing_name):
			existing = frappe.db.get_value(
				"File",
				existing_name,
				[
					"content_hash",
					"file_size",
					"is_private",
					"attached_to_doctype",
					"attached_to_name",
					"attached_to_field",
					"file_url",
				],
				as_dict=True,
			)
			expected = (
				row.get("content_hash"),
				int(row.get("file_size") or 0),
				int(row.get("is_private") or 0),
				target_doctype,
				str(target_name),
				target_field,
			)
			actual = (
				existing.content_hash,
				int(existing.file_size or 0),
				int(existing.is_private or 0),
				existing.attached_to_doctype,
				str(existing.attached_to_name),
				existing.attached_to_field,
			)
			if actual != expected:
				raise MigrationError(
					f"File identity collision for {existing_name}: expected={expected}, actual={actual}"
				)
			existing_doc = frappe.get_doc("File", existing_name)
			if existing_doc.exists_on_disk():
				_update_direct_attachment_field(
					target_doctype, target_name, target_field, existing.file_url
				)
				return {"status": "existing", "file_url": existing.file_url}
			content = _decode_and_validate_file_payload(row)
			if content is None:
				raise MigrationError(
					f"File {existing_name} target metadata exists but its blob is missing"
				)
			existing_doc.flags.new_file = True
			existing_doc.save_file(content=content, ignore_existing_file_check=True)
			frappe.db.set_value(
				"File",
				existing_name,
				{
					"file_name": existing_doc.file_name,
					"file_url": existing_doc.file_url,
					"file_size": existing_doc.file_size,
					"content_hash": existing_doc.content_hash,
				},
				update_modified=False,
			)
			if existing_doc.content_hash != row.get("content_hash"):
				raise MigrationError(f"File {existing_name} changed during blob repair")
			_update_direct_attachment_field(
				target_doctype, target_name, target_field, existing_doc.file_url
			)
			return {"status": "repaired", "file_url": existing_doc.file_url}

		content = _decode_and_validate_file_payload(row)
		blob = frappe.db.get_value(
			"File",
			{
				"content_hash": row.get("content_hash"),
				"is_private": int(row.get("is_private") or 0),
			},
			["name", "file_url"],
			as_dict=True,
		)
		values = {
			"doctype": "File",
			"file_name": row.get("file_name"),
			"file_size": int(row.get("file_size") or 0),
			"content_hash": row.get("content_hash"),
			"is_private": int(row.get("is_private") or 0),
			"attached_to_doctype": target_doctype,
			"attached_to_name": target_name,
			"attached_to_field": target_field,
		}
		file_doc = frappe.get_doc(values)
		if blob:
			file_doc.file_url = blob.file_url
			file_doc.flags.copy_from_existing_file = True
		elif content is not None:
			file_doc.content = content
		else:
			raise MigrationError(
				f"File {existing_name} omitted content before its blob was migrated"
			)
		file_doc.insert(ignore_permissions=True, set_name=existing_name)
		if file_doc.content_hash != row.get("content_hash"):
			raise MigrationError(
				f"File {existing_name} changed content during target creation"
			)
		frappe.db.set_value(
			"File",
			file_doc.name,
			{
				"owner": row.get("owner") or "Administrator",
				"creation": row.get("creation"),
				"modified": row.get("modified"),
				"modified_by": row.get("modified_by") or "Administrator",
			},
			update_modified=False,
		)
		_update_direct_attachment_field(
			target_doctype, target_name, target_field, file_doc.file_url
		)
		return {"status": "created", "file_url": file_doc.file_url}

	def upsert_missing_file_metadata(
		self,
		row: Mapping[str, Any],
		plan: MigrationPlan,
	) -> dict[str, Any]:
		"""Preserve File identity for a locally omitted backup blob."""

		source_doctype = str(row.get("attached_to_doctype") or "")
		if source_doctype not in plan.specs:
			raise MigrationError(
				f"File {row.get('name')} uses unmapped DocType {source_doctype!r}"
			)
		spec = plan.specs[source_doctype]
		target_name = row.get("attached_to_name")
		if not target_name or not frappe.db.exists(spec.target, target_name):
			raise MigrationError(
				f"File {row.get('name')} target {spec.target} {target_name!r} does not exist"
			)
		source_field = row.get("attached_to_field")
		target_field = spec.field_map.get(source_field, source_field) if source_field else None
		self._bulk_upsert(
			"File",
			[
				{
					"name": row.get("name"),
					"file_name": row.get("file_name"),
					"file_url": row.get("file_url"),
					"file_size": int(row.get("file_size") or 0),
					"content_hash": row.get("content_hash"),
					"is_private": int(row.get("is_private") or 0),
					"is_folder": 0,
					"attached_to_doctype": spec.target,
					"attached_to_name": target_name,
					"attached_to_field": target_field,
					"owner": row.get("owner") or "Administrator",
					"creation": row.get("creation"),
					"modified": row.get("modified"),
					"modified_by": row.get("modified_by") or "Administrator",
					"docstatus": 0,
				}
			],
		)
		_update_direct_attachment_field(
			spec.target, target_name, target_field, str(row.get("file_url") or "")
		)
		return {"status": "missing_blob", "file_url": row.get("file_url")}


def run_job(
	migration_name: str,
	mode: str,
	batch_size: int = DEFAULT_BATCH_SIZE,
	allow_missing_files: bool = False,
):
	"""Run one action synchronously; callers normally enqueue this on ``long``."""

	if frappe.local.site != TARGET_SITE:
		raise MigrationError(f"Migration must run on {TARGET_SITE}, not {frappe.local.site}")
	if mode not in {"dry_run", "migrate", "verify"}:
		raise MigrationError(f"Unsupported migration mode {mode!r}")

	migration = frappe.get_doc("MRP Data Migration", migration_name)
	source = F15SourceBridge()
	plan, schema_payload = build_schema_analysis(source_schemas=source.schemas())
	if not plan.ready:
		raise MigrationError("Schema plan is blocked:\n" + "\n".join(plan.issues))
	_validate_live_target_metadata(plan)
	source_status = source.status()
	if source_status.get("site") != SOURCE_SITE:
		raise MigrationError("The source bridge did not connect to the approved source site")
	if mode == "migrate" and not source_status.get("maintenance_mode"):
		raise MigrationError(
			f"{SOURCE_SITE} must be in maintenance mode before the write migration starts"
		)

	_mark_started(migration_name, mode, source_status)
	try:
		if mode == "verify":
			result = _verify_counts(plan, source_status, source, migration_name)
			_mark_complete(migration_name, mode, result)
			return result
		result = _run_documents(
			migration_name,
			plan,
			source,
			dry_run=mode == "dry_run",
			batch_size=max(1, min(int(batch_size), 1000)),
		)
		result["files"] = _run_files(
			migration_name,
			plan,
			source,
			dry_run=mode == "dry_run",
			allow_missing_files=allow_missing_files,
		)
		result["series"] = _run_series(source, dry_run=mode == "dry_run")
		result["schema"] = {
			"source_doctypes": schema_payload["source_doctypes"],
			"target_doctypes": schema_payload["target_doctypes"],
			"migration_kinds": schema_payload["migration_kinds"],
		}
		_mark_complete(migration_name, mode, result)
		return result
	except Exception:
		_mark_failed(migration_name)
		raise


def enqueue_job(migration_name: str, mode: str):
	return frappe.enqueue(
		"essdee_yrp.migration.live.run_job",
		queue="long",
		timeout=86_400,
		job_name=f"mrp-data-migration-{migration_name}-{mode}",
		migration_name=migration_name,
		mode=mode,
	)


def run_attachment_smoke_test(source_file_names: Iterable[str]) -> dict[str, Any]:
	"""Migrate and verify selected source files without starting the full load.

	This diagnostic uses the same F15 bridge and target File lifecycle as the
	production migration. The matching parent documents must already exist on
	the target so the test cannot accidentally pull unrelated business data.
	"""

	if frappe.local.site != TARGET_SITE:
		raise MigrationError(f"Attachment smoke test must run on {TARGET_SITE}")
	names = sorted({str(name) for name in source_file_names if name})
	if not names:
		raise MigrationError("Attachment smoke test needs at least one File name")

	source = F15SourceBridge()
	plan, _schema_payload = build_schema_analysis(source_schemas=source.schemas())
	if not plan.ready:
		raise MigrationError("Schema plan is blocked:\n" + "\n".join(plan.issues))
	_validate_live_target_metadata(plan)
	status = source.file_status(names=names)
	if int(status.get("file_count") or 0) != len(names):
		raise MigrationError(
			"Selected source File count mismatch: "
			f"{status.get('file_count')} != {len(names)}"
		)

	target = FrappeBulkTarget()
	rows = list(source.iter_files(names=names))
	if len(rows) != len(names):
		raise MigrationError(f"Source returned {len(rows)} of {len(names)} selected Files")

	results = []
	for row in rows:
		_validate_file_metadata(row, plan)
		content = _decode_and_validate_file_payload(row)
		outcome = target.upsert_file(row, plan)
		verification = _verify_migrated_file(row, plan, expected_content=content)
		results.append(
			{
				"name": row["name"],
				"status": outcome["status"],
				"file_url": outcome["file_url"],
				"file_size": int(row.get("file_size") or 0),
				"content_hash": row.get("content_hash"),
				"is_private": int(row.get("is_private") or 0),
				"verified": verification,
			}
		)
	frappe.db.commit()
	return {
		"status": "Pass",
		"source_site": SOURCE_SITE,
		"target_site": TARGET_SITE,
		"file_count": len(results),
		"files": results,
	}


def _run_documents(
	migration_name: str,
	plan: MigrationPlan,
	source: F15SourceBridge,
	*,
	dry_run: bool,
	batch_size: int,
) -> dict[str, Any]:
	checkpoint = _load_checkpoint(migration_name) if not dry_run else {"version": 2, "doctypes": {}}
	target = FrappeBulkTarget()
	reference_data = source.reference_data()
	external_reference_count, supporting_external = _validate_external_references(
		plan, source
	)
	counts: dict[str, dict[str, int]] = {}
	processed_total = 0
	preserved_required_values = 0
	historical_required_blanks: dict[str, int] = {}
	skipped_total = (
		sum(int(state.get("processed") or 0) for state in checkpoint["doctypes"].values())
		if not dry_run
		else 0
	)
	failed: list[str] = []
	if not dry_run:
		_ensure_supporting_masters(target)
		_supporting_external_counts = _load_supporting_external_masters(
			target, source, supporting_external, dry_run=False
		)
		frappe.db.commit()
	else:
		_supporting_external_counts = _load_supporting_external_masters(
			target, source, supporting_external, dry_run=True
		)

	for doctype in plan.parent_doctypes:
		spec = plan.specs[doctype]
		state = checkpoint["doctypes"].get(doctype) or {}
		start_after = state.get("last_name") if not dry_run else None
		doctype_count = 0
		batch: list[tuple[dict[str, Any], dict[str, Any]]] = []
		for source_document in source.iter_documents(
			doctype,
			start_after=start_after,
			batch_size=batch_size,
		):
			try:
				target_document = transform_document(source_document, plan)
				preserved_required_values += _resolve_and_validate_required_target_values(
					target_document,
					plan,
					historical_required_blanks,
					reference_data,
				)
			except Exception as exc:
				failed.append(f"{doctype}:{source_document.get('name')}: {exc}")
				if len(failed) >= 100:
					raise MigrationError("Dry-run failure limit reached:\n" + "\n".join(failed))
				continue
			batch.append((source_document, target_document))
			if len(batch) >= batch_size:
				processed = _flush_batch(
					migration_name,
					doctype,
					spec.target,
					batch,
					target,
					checkpoint,
					dry_run,
				)
				doctype_count += processed
				processed_total += processed
				if processed_total % PROGRESS_UPDATE_INTERVAL < processed:
					_update_progress(
						migration_name,
						processed_total + skipped_total,
						skipped_total,
						len(failed),
					)
				batch = []
		if batch:
			processed = _flush_batch(
				migration_name,
				doctype,
				spec.target,
				batch,
				target,
				checkpoint,
				dry_run,
			)
			doctype_count += processed
			processed_total += processed
		counts[doctype] = {"processed": doctype_count, "target_doctype": spec.target}
		_update_progress(
			migration_name,
			processed_total + skipped_total,
			skipped_total,
			len(failed),
		)

	if failed:
		raise MigrationError("Migration transformation failures:\n" + "\n".join(failed))
	return {
		"mode": "dry_run" if dry_run else "migrate",
		"processed": processed_total + skipped_total,
		"skipped": skipped_total,
		"failed": 0,
		"preserved_required_values": preserved_required_values,
		"historical_required_blanks": historical_required_blanks,
		"source_reference_counts": {
			key: len(value) for key, value in reference_data.items()
		},
		"validated_external_reference_values": external_reference_count,
		"supporting_external_masters": _supporting_external_counts,
		"doctypes": counts,
	}


def _validate_external_references(
	plan: MigrationPlan,
	source: F15SourceBridge,
) -> tuple[int, dict[str, set[str]]]:
	planned_targets = {spec.target for spec in plan.specs.values()}
	supported = set(SUPPORTING_EXTERNAL_DOCTYPE_ORDER)
	checked = 0
	failures = []
	missing_supporting: dict[str, set[str]] = {}
	for row in source.iter_external_references():
		source_doctype = str(row.get("source_doctype") or "")
		spec = plan.specs.get(source_doctype)
		if not spec:
			failures.append(f"Unmapped external reference owner {source_doctype}")
			continue
		source_field = str(row.get("fieldname") or "")
		if source_field in spec.ignored_fields:
			continue
		target_fieldname = spec.field_map.get(source_field, source_field)
		target_field = next(
			(
				field
				for field in spec.target_schema.get("fields") or []
				if field.get("fieldname") == target_fieldname
			),
			None,
		)
		if not target_field:
			failures.append(
				f"External reference field has no target: {source_doctype}.{source_field}"
			)
			continue
		if row.get("dynamic"):
			source_link_doctype = str(row.get("link_doctype") or "")
			target_link_doctype = (
				plan.specs[source_link_doctype].target
				if source_link_doctype in plan.specs
				else source_link_doctype
			)
		else:
			target_link_doctype = str(target_field.get("options") or "")
		if not target_link_doctype or target_link_doctype == "File":
			continue
		# These values are created by this same historical load. The source bridge
		# emits only external source masters, but a mapped target field can still
		# point back into the planned graph.
		if target_link_doctype in planned_targets:
			continue
		value = row.get("value")
		checked += 1
		if not frappe.db.exists("DocType", target_link_doctype) or not frappe.db.exists(
			target_link_doctype, value
		):
			if target_link_doctype in supported:
				missing_supporting.setdefault(target_link_doctype, set()).add(str(value))
			else:
				failures.append(
					f"{source_doctype}:{row.get('source_name')}.{source_field} -> "
					f"missing {target_link_doctype} {value}"
				)
			if len(failures) >= 100:
				break
	if failures:
		raise MigrationError(
			"Target is missing external Link masters required by source data:\n"
			+ "\n".join(failures)
		)
	return checked, missing_supporting


def _load_supporting_external_masters(
	target: FrappeBulkTarget,
	source: F15SourceBridge,
	missing: Mapping[str, set[str]],
	*,
	dry_run: bool,
) -> dict[str, int]:
	names_by_doctype = {
		doctype: set(names)
		for doctype, names in missing.items()
		if names
	}
	source_documents: dict[str, list[dict[str, Any]]] = {}

	# Read Users first so their Has Role children can close the dependency set
	# before Role rows are loaded.
	for doctype in SUPPORTING_EXTERNAL_DOCTYPE_ORDER:
		names = names_by_doctype.get(doctype) or set()
		if not names:
			continue
		documents = list(source.iter_supporting_documents(doctype, sorted(names)))
		if len(documents) != len(names):
			raise MigrationError(
				f"Source returned {len(documents)} {doctype} rows for {len(names)} identities"
			)
		source_documents[doctype] = documents
		if doctype == "User":
			for document in documents:
				for row in document.get("roles") or []:
					role = row.get("role")
					if role and not frappe.db.exists("Role", role):
						names_by_doctype.setdefault("Role", set()).add(str(role))

	role_names = names_by_doctype.get("Role") or set()
	if role_names:
		source_documents["Role"] = list(
			source.iter_supporting_documents("Role", sorted(role_names))
		)

	counts = {}
	for doctype in SUPPORTING_EXTERNAL_DOCTYPE_ORDER:
		documents = source_documents.get(doctype) or []
		transformed = [
			_transform_supporting_document(document, doctype)
			for document in documents
		]
		counts[doctype] = len(transformed)
		if not dry_run:
			target.upsert_batch(doctype, transformed)
	return counts


def _transform_supporting_document(
	document: Mapping[str, Any],
	target_doctype: str,
) -> dict[str, Any]:
	meta = frappe.get_meta(target_doctype)
	columns = set() if meta.issingle else set(frappe.db.get_table_columns(target_doctype))
	output: dict[str, Any] = {"doctype": target_doctype}
	for fieldname in (
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
	):
		if fieldname in document:
			output[fieldname] = document[fieldname]
	for field in meta.fields:
		fieldname = field.fieldname
		if not fieldname or fieldname not in document:
			continue
		if field.fieldtype in TABLE_FIELD_TYPES:
			output[fieldname] = [
				_transform_supporting_document(child, field.options)
				for child in document.get(fieldname) or []
			]
		elif meta.issingle or fieldname in columns:
			output[fieldname] = document.get(fieldname)
	password_fields = {
		field.fieldname for field in meta.fields if field.fieldtype == "Password"
	}
	passwords = {
		fieldname: value
		for fieldname, value in (document.get("__migration_passwords") or {}).items()
		if fieldname in password_fields
	}
	if passwords:
		output["__migration_passwords"] = passwords
	return output


def _run_files(
	migration_name: str,
	plan: MigrationPlan,
	source: F15SourceBridge,
	*,
	dry_run: bool,
	allow_missing_files: bool = False,
) -> dict[str, Any]:
	status = source.file_status()
	if status.get("site") != SOURCE_SITE:
		raise MigrationError("F15 file inventory came from an unexpected site")
	checkpoint = _load_checkpoint(migration_name) if not dry_run else {"version": 2, "doctypes": {}}
	file_state = checkpoint.get("files") or {}
	start_after = file_state.get("last_name") if not dry_run else None
	previously_processed = int(file_state.get("processed") or 0) if not dry_run else 0
	target = FrappeBulkTarget()
	processed = 0
	created = 0
	existing = 0
	content_rows = 0
	content_bytes = 0
	missing_file_count = 0
	missing_file_bytes = 0
	missing_content: dict[tuple[str, int], int] = {}

	settings_changed = False
	try:
		if not dry_run:
			_prepare_file_settings(migration_name, checkpoint, status)
			settings_changed = True
		for row in source.iter_files(
			start_after=start_after,
			allow_missing=allow_missing_files,
		):
			_validate_file_metadata(row, plan)
			if row.get("missing_blob"):
				if not allow_missing_files:
					raise MigrationError(
						f"File {row.get('name')} has no source blob"
					)
				missing_file_count += 1
				missing_file_bytes += int(row.get("file_size") or 0)
				missing_content[
					(str(row.get("content_hash") or ""), int(row.get("is_private") or 0))
				] = int(row.get("file_size") or 0)
				if not dry_run:
					target.upsert_missing_file_metadata(row, plan)
					file_state = checkpoint.setdefault("files", {})
					file_state["last_name"] = row["name"]
					file_state["processed"] = int(file_state.get("processed") or 0) + 1
					missing_names = set(file_state.get("missing_blob_names") or [])
					missing_names.add(row["name"])
					file_state["missing_blob_names"] = sorted(missing_names)
					frappe.db.set_value(
						"MRP Data Migration",
						migration_name,
						"checkpoint_json",
						json.dumps(checkpoint, sort_keys=True),
						update_modified=False,
					)
					frappe.db.commit()
				processed += 1
				continue
			content = _decode_and_validate_file_payload(row)
			if content is not None:
				content_rows += 1
				content_bytes += len(content)
			if not dry_run:
				outcome = target.upsert_file(row, plan)
				if outcome["status"] in {"created", "repaired"}:
					created += 1
				else:
					existing += 1
				file_state = checkpoint.setdefault("files", {})
				file_state["last_name"] = row["name"]
				file_state["processed"] = int(file_state.get("processed") or 0) + 1
				frappe.db.set_value(
					"MRP Data Migration",
					migration_name,
					"checkpoint_json",
					json.dumps(checkpoint, sort_keys=True),
					update_modified=False,
				)
				frappe.db.commit()
			processed += 1
		if dry_run:
			if processed != int(status.get("file_count") or 0):
				raise MigrationError(
					f"File dry-run count mismatch: {processed} != {status.get('file_count')}"
				)
			observed_content_count = content_rows + len(missing_content)
			observed_content_bytes = content_bytes + sum(missing_content.values())
			if observed_content_count != int(status.get("unique_content_count") or 0):
				raise MigrationError(
					"File dry-run unique-content count mismatch: "
					f"{observed_content_count} != {status.get('unique_content_count')}"
				)
			if observed_content_bytes != int(status.get("unique_content_bytes") or 0):
				raise MigrationError(
					"File dry-run byte mismatch: "
					f"{observed_content_bytes} != {status.get('unique_content_bytes')}"
				)
		else:
			_repair_file_links(plan)
			frappe.db.commit()
	finally:
		if settings_changed:
			_restore_file_settings(migration_name, checkpoint)

	return {
		"processed": processed + previously_processed,
		"created": created,
		"existing": existing,
		"source_file_count": int(status.get("file_count") or 0),
		"source_file_bytes": int(status.get("file_bytes") or 0),
		"unique_content_count": int(status.get("unique_content_count") or 0),
		"unique_content_bytes": int(status.get("unique_content_bytes") or 0),
		"max_file_size": int(status.get("max_file_size") or 0),
		"missing_source_blob_count": missing_file_count,
		"missing_source_blob_bytes": missing_file_bytes,
		"missing_unique_content_count": len(missing_content),
		"missing_unique_content_bytes": sum(missing_content.values()),
		"missing_file_policy": "Audited Local Backup Omission"
		if allow_missing_files
		else "Strict",
	}


def _run_series(source: F15SourceBridge, *, dry_run: bool) -> dict[str, Any]:
	"""Merge F15 naming counters without ever reducing a target counter."""

	rows = []
	for row in source.iter_series():
		name = str(row.get("name") or "")
		try:
			current = int(row.get("current") or 0)
		except (TypeError, ValueError) as exc:
			raise MigrationError(f"Source tabSeries {name!r} has invalid current") from exc
		if current < 0:
			raise MigrationError(f"Source tabSeries {name!r} has negative current")
		rows.append((name, current))

	target_advanced = 0
	target_already_ahead = 0
	for name, current in rows:
		target_current = _get_target_series_current(name)
		if target_current is not None and int(target_current or 0) >= current:
			target_already_ahead += 1
		else:
			target_advanced += 1
	if not dry_run and rows:
		for chunk in _chunks(rows, 1000):
			placeholders = ", ".join(["(%s, %s)"] * len(chunk))
			values = [value for row in chunk for value in row]
			frappe.db.sql(
				f"INSERT INTO `tabSeries` (`name`, `current`) VALUES {placeholders} "
				"ON DUPLICATE KEY UPDATE `current`=GREATEST(`current`, VALUES(`current`))",
				values,
			)
		frappe.db.commit()
	return {
		"source_series_count": len(rows),
		"target_counters_to_advance": target_advanced,
		"target_counters_already_equal_or_ahead": target_already_ahead,
		"merge_rule": "GREATEST(target_current, source_current)",
		"writes": not dry_run,
	}


def _get_target_series_current(name: str) -> int | None:
	rows = frappe.db.sql(
		"SELECT `current` FROM `tabSeries` WHERE `name`=%s",
		(name,),
	)
	return int(rows[0][0] or 0) if rows else None


def _validate_file_metadata(row: Mapping[str, Any], plan: MigrationPlan) -> None:
	required = (
		"name",
		"file_name",
		"content_hash",
		"attached_to_doctype",
		"attached_to_name",
	)
	missing = [fieldname for fieldname in required if not row.get(fieldname)]
	if missing:
		raise MigrationError(
			f"File {row.get('name')} has blank required metadata: {', '.join(missing)}"
		)
	if row.get("attached_to_doctype") not in plan.specs:
		raise MigrationError(
			f"File {row.get('name')} has unmapped attachment DocType "
			f"{row.get('attached_to_doctype')}"
		)


def _decode_and_validate_file_payload(row: Mapping[str, Any]) -> bytes | None:
	encoded = row.get("content_base64")
	if encoded is None:
		return None
	try:
		content = base64.b64decode(encoded, validate=True)
	except (TypeError, ValueError) as exc:
		raise MigrationError(f"File {row.get('name')} contains invalid base64") from exc
	actual_hash = hashlib.md5(content, usedforsecurity=False).hexdigest()
	if actual_hash != row.get("content_hash"):
		raise MigrationError(
			f"File {row.get('name')} content hash mismatch after transport"
		)
	if len(content) != int(row.get("file_size") or 0):
		raise MigrationError(
			f"File {row.get('name')} size mismatch after transport: "
			f"{len(content)} != {row.get('file_size')}"
		)
	return content


def _verify_migrated_file(
	row: Mapping[str, Any],
	plan: MigrationPlan,
	*,
	expected_content: bytes | None = None,
) -> dict[str, bool]:
	spec = plan.specs[str(row["attached_to_doctype"])]
	target_field = (
		spec.field_map.get(row.get("attached_to_field"), row.get("attached_to_field"))
		if row.get("attached_to_field")
		else None
	)
	target = frappe.db.get_value(
		"File",
		row["name"],
		[
			"content_hash",
			"file_size",
			"is_private",
			"attached_to_doctype",
			"attached_to_name",
			"attached_to_field",
			"file_url",
		],
		as_dict=True,
	)
	if not target:
		raise MigrationError(f"Migrated File {row['name']} is missing on target")
	expected = (
		row.get("content_hash"),
		int(row.get("file_size") or 0),
		int(row.get("is_private") or 0),
		spec.target,
		str(row.get("attached_to_name")),
		target_field,
	)
	actual = (
		target.content_hash,
		int(target.file_size or 0),
		int(target.is_private or 0),
		target.attached_to_doctype,
		str(target.attached_to_name),
		target.attached_to_field,
	)
	if actual != expected:
		raise MigrationError(
			f"Migrated File {row['name']} metadata mismatch: expected={expected}, actual={actual}"
		)
	file_doc = frappe.get_doc("File", row["name"])
	if not file_doc.exists_on_disk():
		raise MigrationError(f"Migrated File {row['name']} has no target blob")
	# File.get_content tries text encodings by default. A binary payload that
	# happens to decode as latin-1 must still be compared as its original bytes.
	target_content = file_doc.get_content(encodings=[])
	if isinstance(target_content, str):
		target_content = target_content.encode()
	actual_hash = hashlib.md5(target_content, usedforsecurity=False).hexdigest()
	if actual_hash != row.get("content_hash") or len(target_content) != int(
		row.get("file_size") or 0
	):
		raise MigrationError(f"Migrated File {row['name']} target blob changed")
	if expected_content is not None and target_content != expected_content:
		raise MigrationError(f"Migrated File {row['name']} bytes differ from source")
	url_prefix = "/private/files/" if int(row.get("is_private") or 0) else "/files/"
	if not str(target.file_url or "").startswith(url_prefix):
		raise MigrationError(
			f"Migrated File {row['name']} has invalid privacy URL {target.file_url!r}"
		)
	if target_field:
		field = frappe.get_meta(spec.target).get_field(target_field)
		if field and field.fieldtype in {"Attach", "Attach Image"}:
			field_value = frappe.db.get_value(
				spec.target,
				row.get("attached_to_name"),
				target_field,
			)
			if field_value != target.file_url:
				raise MigrationError(
					f"Migrated File {row['name']} did not repair "
					f"{spec.target}.{target_field}"
				)
	return {
		"metadata": True,
		"blob_exists": True,
		"hash": True,
		"size": True,
		"privacy_url": True,
		"direct_attachment_field": True,
	}


def _prepare_file_settings(
	migration_name: str,
	checkpoint: dict[str, Any],
	status: Mapping[str, Any],
) -> None:
	settings = checkpoint.setdefault("file_settings", {})
	if "original_max_file_size" not in settings:
		settings["original_max_file_size"] = frappe.db.get_single_value(
			"System Settings", "max_file_size"
		)
		settings["original_strip_exif"] = frappe.db.get_single_value(
			"System Settings", "strip_exif_metadata_from_uploaded_images"
		)
	required_megabytes = max(
		25,
		math.ceil(int(status.get("max_file_size") or 0) / (1024 * 1024)),
	)
	frappe.db.set_single_value("System Settings", "max_file_size", required_megabytes)
	# Historical bytes must remain byte-identical; uploading an existing JPEG a
	# second time must not rewrite it through the current EXIF policy.
	frappe.db.set_single_value(
		"System Settings", "strip_exif_metadata_from_uploaded_images", 0
	)
	settings["temporary_max_file_size"] = required_megabytes
	settings["restored"] = False
	frappe.db.set_value(
		"MRP Data Migration",
		migration_name,
		"checkpoint_json",
		json.dumps(checkpoint, sort_keys=True),
		update_modified=False,
	)
	_clear_system_settings_cache()
	frappe.db.commit()


def _restore_file_settings(migration_name: str, checkpoint: dict[str, Any]) -> None:
	settings = checkpoint.get("file_settings") or {}
	if "original_max_file_size" not in settings:
		return
	frappe.db.set_single_value(
		"System Settings", "max_file_size", settings.get("original_max_file_size")
	)
	frappe.db.set_single_value(
		"System Settings",
		"strip_exif_metadata_from_uploaded_images",
		settings.get("original_strip_exif"),
	)
	settings["restored"] = True
	frappe.db.set_value(
		"MRP Data Migration",
		migration_name,
		"checkpoint_json",
		json.dumps(checkpoint, sort_keys=True),
		update_modified=False,
	)
	_clear_system_settings_cache()
	frappe.db.commit()


def _clear_system_settings_cache() -> None:
	frappe.clear_document_cache("System Settings", "System Settings")
	if hasattr(frappe.local, "system_settings"):
		del frappe.local.system_settings


def _update_direct_attachment_field(
	target_doctype: str,
	target_name: str,
	target_field: str | None,
	file_url: str,
) -> None:
	if not target_field:
		return
	field = frappe.get_meta(target_doctype).get_field(target_field)
	if not field or field.fieldtype not in {"Attach", "Attach Image"}:
		return
	frappe.db.set_value(
		target_doctype,
		target_name,
		target_field,
		file_url,
		update_modified=False,
	)


def _repair_file_links(plan: MigrationPlan) -> None:
	"""Point copied Attach fields at the File URL created on this site."""

	for target_doctype in sorted({spec.target for spec in plan.specs.values()}):
		meta = frappe.get_meta(target_doctype)
		if meta.issingle or meta.istable:
			continue
		for field in meta.fields:
			if field.fieldtype not in {"Attach", "Attach Image"}:
				continue
			frappe.db.sql(
				f"UPDATE {_quote_identifier('tab' + target_doctype)} target "
				"INNER JOIN `tabFile` file ON file.attached_to_doctype=%s "
				"AND file.attached_to_name=target.name AND file.attached_to_field=%s "
				f"SET target.{_quote_identifier(field.fieldname)}=file.file_url",
				(target_doctype, field.fieldname),
			)

	# These source child tables store both a stable File identity and its fetched
	# URL, while the File itself is attached to the parent table field.
	for child_doctype, link_field, url_field in (
		("Product Design", "file", "graphic_image"),
		("Product File Version", "file", "file_url"),
	):
		if not frappe.db.exists("DocType", child_doctype):
			continue
		frappe.db.sql(
			f"UPDATE {_quote_identifier('tab' + child_doctype)} child "
			"INNER JOIN `tabFile` file "
			f"ON file.name=child.{_quote_identifier(link_field)} "
			f"SET child.{_quote_identifier(url_field)}=file.file_url"
		)


def _flush_batch(
	migration_name: str,
	source_doctype: str,
	target_doctype: str,
	batch: list[tuple[dict[str, Any], dict[str, Any]]],
	target: FrappeBulkTarget,
	checkpoint: dict[str, Any],
	dry_run: bool,
) -> int:
	if dry_run:
		return len(batch)
	target.upsert_batch(target_doctype, [target_doc for _source, target_doc in batch])
	state = checkpoint["doctypes"].setdefault(source_doctype, {})
	state["last_name"] = batch[-1][0]["name"]
	state["processed"] = int(state.get("processed") or 0) + len(batch)
	state["target_doctype"] = target_doctype
	frappe.db.set_value(
		"MRP Data Migration",
		migration_name,
		"checkpoint_json",
		json.dumps(checkpoint, sort_keys=True),
		update_modified=False,
	)
	frappe.db.commit()
	return len(batch)


def _validate_live_target_metadata(plan: MigrationPlan) -> None:
	missing = []
	for target_doctype in sorted({spec.target for spec in plan.specs.values()}):
		if not frappe.db.exists("DocType", target_doctype):
			missing.append(f"DocType {target_doctype}")
			continue
		meta = frappe.get_meta(target_doctype)
		if meta.issingle:
			continue
		columns = set(frappe.db.get_table_columns(target_doctype))
		for field in plan.target_schemas[target_doctype].get("fields") or []:
			if (
				field.get("fieldname")
				and field.get("fieldtype") not in NO_COLUMN_FIELD_TYPES | TABLE_FIELD_TYPES
				and field["fieldname"] not in columns
			):
				missing.append(f"{target_doctype}.{field['fieldname']}")
	if missing:
		raise MigrationError(
			"Target metadata is not synced; missing physical fields: " + ", ".join(missing[:50])
		)


def _resolve_and_validate_required_target_values(
	document: dict[str, Any],
	plan: MigrationPlan,
	historical_required_blanks: dict[str, int] | None = None,
	reference_data: Mapping[str, Mapping[str, Any]] | None = None,
) -> int:
	target_schema = plan.target_schemas[str(document["doctype"])]
	preserved = _validate_required_target_values(
		document, target_schema, historical_required_blanks, reference_data
	)
	for field in target_schema.get("fields") or []:
		if field.get("fieldtype") not in TABLE_FIELD_TYPES:
			continue
		for child in document.get(str(field.get("fieldname"))) or []:
			preserved += _resolve_and_validate_required_target_values(
				child, plan, historical_required_blanks, reference_data
			)
	return preserved


def _validate_required_target_values(
	document: dict[str, Any],
	target_schema: Mapping[str, Any],
	historical_required_blanks: dict[str, int] | None = None,
	reference_data: Mapping[str, Mapping[str, Any]] | None = None,
) -> int:
	preserved = 0
	for field in target_schema.get("fields") or []:
		if not field.get("reqd") or field.get("fieldtype") in TABLE_FIELD_TYPES:
			continue
		if field.get("default") not in (None, ""):
			continue
		fieldname = field.get("fieldname")
		if not fieldname or document.get(fieldname) not in (None, ""):
			continue
		derived = _derive_required_value(document, fieldname, reference_data)
		if derived not in (None, ""):
			document[fieldname] = derived
			preserved += 1
			continue
		existing = None
		if target_schema.get("issingle"):
			existing = frappe.db.get_single_value(str(target_schema["name"]), fieldname)
		elif document.get("name"):
			existing = frappe.db.get_value(
				str(target_schema["name"]), document["name"], fieldname
			)
		if existing not in (None, ""):
			document[fieldname] = existing
			preserved += 1
			continue
		if _is_valid_historical_required_blank(document, fieldname):
			if historical_required_blanks is not None:
				key = f"{document.get('doctype')}.{fieldname}"
				historical_required_blanks[key] = historical_required_blanks.get(key, 0) + 1
			continue
		if fieldname:
			raise MigrationError(
				f"{document.get('doctype')} {document.get('name')} has no required {fieldname}"
			)
	return preserved


def _derive_required_value(
	document: Mapping[str, Any],
	fieldname: str,
	reference_data: Mapping[str, Mapping[str, Any]] | None = None,
) -> Any:
	reference_data = reference_data or {}
	if fieldname == "received_type":
		# Production API's configured stock default is Accepted. Legacy Stock
		# Entry rows and ordinary WO deliverables often omitted the explicit
		# value; nonblank rejection/mistake types pass through untouched.
		return DEFAULT_RECEIVED_TYPE
	if (
		document.get("doctype") == "Cut Panel Movement"
		and fieldname == "from_warehouse"
	):
		return reference_data.get("cut_panel_from_warehouse", {}).get(
			str(document.get("name"))
		)
	if fieldname == "uom":
		item_variant = (
			document.get("item_variant")
			or document.get("item")
			or document.get("item_name")
		)
		if item_variant:
			item = reference_data.get("variant_to_item", {}).get(str(item_variant))
			if not item:
				item = frappe.db.get_value("Item Variant", item_variant, "item")
			if not item and frappe.db.exists("Item", item_variant):
				item = item_variant
			if item:
				source_uom = reference_data.get("item_defaults", {}).get(str(item))
				if source_uom:
					return source_uom
				return frappe.db.get_value("Item", item, "default_unit_of_measure")
	if document.get("doctype") == "Purchase Invoice Item" and fieldname == "item_group":
		item = reference_data.get("variant_to_item", {}).get(str(document.get("item")))
		if not item:
			item = frappe.db.get_value("Item Variant", document.get("item"), "item")
		if item:
			source_group = reference_data.get("item_groups", {}).get(str(item))
			if source_group:
				return source_group
			return frappe.db.get_value("Item", item, "item_group")
	if document.get("doctype") == "Lot BOM" and fieldname == "process_name":
		item = reference_data.get("variant_to_item", {}).get(
			str(document.get("item_name"))
		)
		if not item:
			item = frappe.db.get_value("Item Variant", document.get("item_name"), "item")
		if not item:
			return None
		item_group = reference_data.get("item_groups", {}).get(str(item))
		if not item_group:
			item_group = frappe.db.get_value("Item", item, "item_group")
		if item_group == "Purchase Accessories":
			return "Packing"
	return None


def _is_valid_historical_required_blank(
	document: Mapping[str, Any], fieldname: str
) -> bool:
	cutoff = LEGACY_REQUIRED_FIELD_CUTOFFS.get(
		(str(document.get("doctype")), fieldname)
	)
	creation = document.get("creation")
	return bool(cutoff and creation and get_datetime(creation) < cutoff)


def _ensure_supporting_masters(target: FrappeBulkTarget) -> None:
	now = now_datetime()
	target._bulk_upsert(
		"Bill Tracking Received Via",
		[
			{
				"name": name,
				"received_via": name,
				"owner": "Administrator",
				"creation": now,
				"modified": now,
				"modified_by": "Administrator",
				"docstatus": 0,
			}
			for name in SUPPORTING_BILL_RECEIVED_VIA
		],
	)
	if not frappe.db.exists("Received Type", DEFAULT_RECEIVED_TYPE):
		# The actual ten source records are migrated through GRN Item Type. This
		# early row only satisfies dependency checks if another DocType sorts first.
		target._bulk_upsert(
			"Received Type",
			[
				{
					"name": DEFAULT_RECEIVED_TYPE,
					"received_type_name": DEFAULT_RECEIVED_TYPE,
					"owner": "Administrator",
					"creation": now,
					"modified": now,
					"modified_by": "Administrator",
					"docstatus": 0,
				}
			],
		)


def _verify_counts(
	plan: MigrationPlan,
	source_status: Mapping[str, Any],
	source: F15SourceBridge,
	migration_name: str,
) -> dict[str, Any]:
	identity = _verify_source_identities(plan, source, migration_name)
	checkpoint = _load_checkpoint(migration_name)
	missing_blob_names = set(
		(checkpoint.get("files") or {}).get("missing_blob_names") or []
	)
	files = _verify_files(plan, source, allowed_missing_blob_names=missing_blob_names)
	series = _verify_series(source)
	stock = _verify_stock_summary(source)
	links = _verify_link_integrity(plan)
	failures = [
		*identity["failures"],
		*files["failures"],
		*links["failures"],
		*series["failures"],
	]
	if stock["status"] != "Pass":
		failures.append("Stock bucket digest or totals do not match")
	if failures:
		raise MigrationError(
			"Post-migration verification failed:\n" + "\n".join(failures[:100])
		)
	return {
		"mode": "verify",
		"status": "Verified",
		"processed": identity["verified_parent_records"],
		"failed": 0,
		"source_total_parent_records": int(source_status.get("total_parent_records") or 0),
		"identities": identity,
		"files": files,
		"series": series,
		"stock": stock,
		"links": links,
	}


def _verify_series(source: F15SourceBridge) -> dict[str, Any]:
	failures = []
	verified = 0
	for row in source.iter_series():
		name = str(row.get("name") or "")
		source_current = int(row.get("current") or 0)
		target_current = _get_target_series_current(name)
		if target_current is None or int(target_current or 0) < source_current:
			failures.append(
				f"Naming series {name!r}: target={target_current}, source={source_current}"
			)
		verified += 1
		if len(failures) >= 100:
			break
	return {
		"status": "Pass" if not failures else "Failed",
		"verified_source_series": verified,
		"failures": failures,
	}


def _verify_source_identities(
	plan: MigrationPlan,
	source: F15SourceBridge,
	migration_name: str,
	batch_size: int = 1000,
) -> dict[str, Any]:
	expected_counts: dict[str, int] = {}
	missing_counts: dict[str, int] = {}
	failures: list[str] = []
	verified_parents = 0
	pending: dict[str, list[str]] = {}

	def flush() -> None:
		for target_doctype, names in list(pending.items()):
			if not names:
				continue
			for chunk in _chunks(list(dict.fromkeys(names)), 500):
				found = set(
					frappe.get_all(
						target_doctype,
						filters={"name": ["in", chunk]},
						pluck="name",
						limit_page_length=0,
					)
				)
				missing = [name for name in chunk if name not in found]
				if missing:
					missing_counts[target_doctype] = (
						missing_counts.get(target_doctype, 0) + len(missing)
					)
					for name in missing[: max(0, 100 - len(failures))]:
						failures.append(f"Missing {target_doctype} {name}")
		pending.clear()

	for source_doctype in plan.parent_doctypes:
		for source_document in source.iter_documents(
			source_doctype, batch_size=batch_size
		):
			target_document = transform_document(source_document, plan)
			_collect_document_identities(target_document, plan, pending, expected_counts)
			verified_parents += 1
			if verified_parents % batch_size == 0:
				flush()
			if verified_parents % PROGRESS_UPDATE_INTERVAL == 0:
				_update_progress(migration_name, verified_parents, 0, len(failures))
		flush()

	rows = []
	for target_doctype, expected_count in sorted(expected_counts.items()):
		target_meta = frappe.get_meta(target_doctype)
		target_count = 1 if target_meta.issingle else frappe.db.count(target_doctype)
		missing = missing_counts.get(target_doctype, 0)
		target_only = max(0, target_count - expected_count + missing)
		if target_only:
			failures.append(
				f"Unexpected target-only rows in {target_doctype}: {target_only}"
			)
		rows.append(
			{
				"target_doctype": target_doctype,
				"source_identity_count": expected_count,
				"target_count": target_count,
				"target_only_count": target_only,
				"missing_source_identities": missing,
				"status": "Pass" if not missing and not target_only else "Failed",
			}
		)
	return {
		"verified_parent_records": verified_parents,
		"verified_parent_and_child_identities": sum(expected_counts.values()),
		"doctypes": rows,
		"failures": failures,
	}


def _collect_document_identities(
	document: Mapping[str, Any],
	plan: MigrationPlan,
	pending: dict[str, list[str]],
	expected_counts: dict[str, int],
) -> None:
	doctype = str(document["doctype"])
	name = document.get("name")
	if name:
		pending.setdefault(doctype, []).append(str(name))
		expected_counts[doctype] = expected_counts.get(doctype, 0) + 1
	schema = plan.target_schemas[doctype]
	for field in schema.get("fields") or []:
		if field.get("fieldtype") not in TABLE_FIELD_TYPES:
			continue
		for child in document.get(str(field.get("fieldname"))) or []:
			_collect_document_identities(child, plan, pending, expected_counts)


def _verify_files(
	plan: MigrationPlan,
	source: F15SourceBridge,
	*,
	allowed_missing_blob_names: set[str] | None = None,
) -> dict[str, Any]:
	status = source.file_status()
	allowed_missing_blob_names = allowed_missing_blob_names or set()
	failures = []
	verified = 0
	verified_blobs = 0
	audited_missing_blobs = 0
	for row in source.iter_files(metadata_only=True):
		_validate_file_metadata(row, plan)
		spec = plan.specs[str(row["attached_to_doctype"])]
		target_field = (
			spec.field_map.get(row.get("attached_to_field"), row.get("attached_to_field"))
			if row.get("attached_to_field")
			else None
		)
		target = frappe.db.get_value(
			"File",
			row["name"],
			[
				"content_hash",
				"file_size",
				"is_private",
				"attached_to_doctype",
				"attached_to_name",
				"attached_to_field",
			],
			as_dict=True,
		)
		if not target:
			failures.append(f"Missing File {row['name']}")
		elif (
			target.content_hash != row.get("content_hash")
			or int(target.file_size or 0) != int(row.get("file_size") or 0)
			or int(target.is_private or 0) != int(row.get("is_private") or 0)
			or target.attached_to_doctype != spec.target
			or str(target.attached_to_name) != str(row.get("attached_to_name"))
			or target.attached_to_field != target_field
		):
			failures.append(f"File metadata mismatch {row['name']}")
		elif not frappe.get_doc("File", row["name"]).exists_on_disk():
			if row["name"] in allowed_missing_blob_names:
				audited_missing_blobs += 1
			else:
				failures.append(f"File blob missing on disk {row['name']}")
		else:
			verified_blobs += 1
		verified += 1
		if len(failures) >= 100:
			break
	return {
		"source_file_count": int(status.get("file_count") or 0),
		"verified_file_count": verified,
		"verified_blob_count": verified_blobs,
		"audited_missing_blob_count": audited_missing_blobs,
		"source_file_bytes": int(status.get("file_bytes") or 0),
		"status": (
			"Pass With Audited Missing Blobs"
			if not failures
			and verified == int(status.get("file_count") or 0)
			and audited_missing_blobs
			else "Pass"
			if not failures and verified == int(status.get("file_count") or 0)
			else "Failed"
		),
		"failures": failures,
	}


def _verify_stock_summary(source: F15SourceBridge) -> dict[str, Any]:
	source_summary = source.stock_summary()
	prefix = str(source_summary.get("ledger_name_prefix") or "")
	if not prefix:
		raise MigrationError("Source stock summary omitted its ledger identity prefix")
	target_summary = _target_stock_summary(prefix)
	keys = (
		"bucket_count",
		"bucket_digest",
		"total_qty",
		"total_stock_value_difference",
	)
	matches = all(str(source_summary.get(key)) == str(target_summary.get(key)) for key in keys)
	return {
		"status": "Pass" if matches else "Failed",
		"source": source_summary,
		"target_source_ledger_subset": target_summary,
		"target_non_source_ledger_rows": frappe.db.count(
			"Stock Ledger Entry", {"name": ["not like", f"{prefix}%"]}
		),
	}


def _target_stock_summary(prefix: str) -> dict[str, Any]:
	digest = hashlib.sha256()
	total_qty = Decimal("0")
	total_value = Decimal("0")
	rows = frappe.db.sql(
		"""
		SELECT item, warehouse, COALESCE(lot, ''), COALESCE(received_type, ''),
			SUM(qty), SUM(stock_value_difference)
		FROM `tabStock Ledger Entry`
		WHERE COALESCE(is_cancelled, 0) = 0 AND name LIKE %s
		GROUP BY item, warehouse, lot, received_type
		ORDER BY item, warehouse, lot, received_type
		""",
		(f"{prefix}%",),
	)
	for item, warehouse, lot, received_type, qty, stock_value in rows:
		qty = Decimal(str(qty or 0)).quantize(Decimal("0.000000001"))
		stock_value = Decimal(str(stock_value or 0)).quantize(Decimal("0.000000001"))
		total_qty += qty
		total_value += stock_value
		payload = [
			item or "",
			warehouse or "",
			lot or "",
			received_type or "",
			format(qty, "f"),
			format(stock_value, "f"),
		]
		digest.update(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
		digest.update(b"\n")
	return {
		"bucket_count": len(rows),
		"bucket_digest": digest.hexdigest(),
		"total_qty": format(total_qty, "f"),
		"total_stock_value_difference": format(total_value, "f"),
	}


def _verify_link_integrity(plan: MigrationPlan) -> dict[str, Any]:
	"""Check every static and dynamic Link in the migrated target schemas."""

	failures: list[str] = []
	checked_fields = 0
	broken_values = 0
	for doctype in sorted({spec.target for spec in plan.specs.values()}):
		schema = plan.target_schemas[doctype]
		meta = frappe.get_meta(doctype)
		fields = {
			field.get("fieldname"): field
			for field in schema.get("fields") or []
			if field.get("fieldname")
		}
		for fieldname, field in fields.items():
			fieldtype = field.get("fieldtype")
			if fieldtype == "Link" and field.get("options"):
				checked_fields += 1
				broken = _broken_static_link_count(
					doctype,
					fieldname,
					str(field["options"]),
					is_single=bool(meta.issingle),
				)
				if broken:
					broken_values += broken[0]
					failures.append(
						f"Broken Link {doctype}.{fieldname} -> {field['options']}: "
						f"{broken[0]} values; samples={broken[1]}"
					)
			elif fieldtype == "Dynamic Link" and field.get("options"):
				checked_fields += 1
				broken = _broken_dynamic_link_count(
					doctype,
					fieldname,
					str(field["options"]),
					is_single=bool(meta.issingle),
				)
				if broken:
					broken_values += broken[0]
					failures.append(
						f"Broken Dynamic Link {doctype}.{fieldname}: "
						f"{broken[0]} values; samples={broken[1]}"
					)
	return {
		"status": "Pass" if not failures else "Failed",
		"checked_link_fields": checked_fields,
		"broken_link_values": broken_values,
		"failures": failures,
	}


def _broken_static_link_count(
	doctype: str,
	fieldname: str,
	link_doctype: str,
	*,
	is_single: bool,
) -> tuple[int, list[str]] | None:
	if not frappe.db.exists("DocType", link_doctype):
		return 1, [f"missing target DocType {link_doctype}"]
	if is_single:
		value = frappe.db.get_single_value(doctype, fieldname)
		if value and not frappe.db.exists(link_doctype, value):
			return 1, [str(value)]
		return None
	table = _quote_identifier("tab" + doctype)
	field = _quote_identifier(fieldname)
	link_table = _quote_identifier("tab" + link_doctype)
	count = int(
		frappe.db.sql(
			f"SELECT COUNT(*) FROM {table} source "
			f"LEFT JOIN {link_table} linked ON linked.name=source.{field} "
			f"WHERE COALESCE(source.{field}, '')<>'' AND linked.name IS NULL"
		)[0][0]
	)
	if not count:
		return None
	samples = frappe.db.sql(
		f"SELECT source.name, source.{field} FROM {table} source "
		f"LEFT JOIN {link_table} linked ON linked.name=source.{field} "
		f"WHERE COALESCE(source.{field}, '')<>'' AND linked.name IS NULL LIMIT 10"
	)
	return count, [f"{name}={value}" for name, value in samples]


def _broken_dynamic_link_count(
	doctype: str,
	fieldname: str,
	controller_fieldname: str,
	*,
	is_single: bool,
) -> tuple[int, list[str]] | None:
	if is_single:
		controller = frappe.db.get_single_value(doctype, controller_fieldname)
		value = frappe.db.get_single_value(doctype, fieldname)
		if value and (
			not controller
			or not frappe.db.exists("DocType", controller)
			or not frappe.db.exists(controller, value)
		):
			return 1, [f"{controller}:{value}"]
		return None
	table = _quote_identifier("tab" + doctype)
	field = _quote_identifier(fieldname)
	controller_field = _quote_identifier(controller_fieldname)
	controllers = frappe.db.sql(
		f"SELECT DISTINCT source.{controller_field} FROM {table} source "
		f"WHERE COALESCE(source.{field}, '')<>''"
	)
	total = 0
	samples: list[str] = []
	for (controller,) in controllers:
		if not controller or not frappe.db.exists("DocType", controller):
			count = int(
				frappe.db.sql(
					f"SELECT COUNT(*) FROM {table} source WHERE source.{controller_field}=%s "
					f"AND COALESCE(source.{field}, '')<>''",
					(controller,),
				)[0][0]
			)
			total += count
			samples.append(f"missing DocType {controller} ({count})")
			continue
		link_table = _quote_identifier("tab" + str(controller))
		count = int(
			frappe.db.sql(
				f"SELECT COUNT(*) FROM {table} source "
				f"LEFT JOIN {link_table} linked ON linked.name=source.{field} "
				f"WHERE source.{controller_field}=%s AND COALESCE(source.{field}, '')<>'' "
				"AND linked.name IS NULL",
				(controller,),
			)[0][0]
		)
		if not count:
			continue
		total += count
		if len(samples) < 10:
			rows = frappe.db.sql(
				f"SELECT source.name, source.{field} FROM {table} source "
				f"LEFT JOIN {link_table} linked ON linked.name=source.{field} "
				f"WHERE source.{controller_field}=%s AND COALESCE(source.{field}, '')<>'' "
				"AND linked.name IS NULL LIMIT 10",
				(controller,),
			)
			samples.extend(f"{controller}:{name}={value}" for name, value in rows)
	return (total, samples[:10]) if total else None


def _load_checkpoint(migration_name: str) -> dict[str, Any]:
	value = frappe.db.get_value("MRP Data Migration", migration_name, "checkpoint_json")
	if not value:
		return {"version": 2, "doctypes": {}}
	checkpoint = json.loads(value)
	if checkpoint.get("version") != 2 or not isinstance(checkpoint.get("doctypes"), dict):
		raise MigrationError("Unsupported or malformed migration checkpoint")
	return checkpoint


def _mark_started(migration_name: str, mode: str, source_status: Mapping[str, Any]) -> None:
	action = {"dry_run": "Dry Run", "migrate": "Migrate", "verify": "Verify"}[mode]
	frappe.db.set_value(
		"MRP Data Migration",
		migration_name,
		{
			"status": "Running",
			"last_action": action,
			"last_started_on": now_datetime(),
			"last_completed_on": None,
			"total_source_records": source_status.get("total_parent_records") or 0,
			"processed_records": 0,
			"skipped_records": 0,
			"failed_records": 0,
			"error_log": None,
		},
		update_modified=False,
	)
	frappe.db.commit()


def _update_progress(migration_name: str, processed: int, skipped: int, failed: int) -> None:
	frappe.db.set_value(
		"MRP Data Migration",
		migration_name,
		{
			"processed_records": processed,
			"skipped_records": skipped,
			"failed_records": failed,
		},
		update_modified=False,
	)
	frappe.db.commit()


def _mark_complete(migration_name: str, mode: str, result: Mapping[str, Any]) -> None:
	status = {"dry_run": "Dry Run Complete", "migrate": "Completed", "verify": "Verified"}[mode]
	frappe.db.set_value(
		"MRP Data Migration",
		migration_name,
		{
			"status": status,
			"last_completed_on": now_datetime(),
			"processed_records": result.get("processed") or 0,
			"skipped_records": result.get("skipped") or 0,
			"failed_records": result.get("failed") or 0,
			"report_json": json.dumps(result, sort_keys=True, default=str),
			"error_log": None,
		},
		update_modified=False,
	)
	frappe.db.commit()


def _mark_failed(migration_name: str) -> None:
	frappe.db.rollback()
	frappe.db.set_value(
		"MRP Data Migration",
		migration_name,
		{
			"status": "Failed",
			"last_completed_on": now_datetime(),
			"failed_records": 1,
			"error_log": frappe.get_traceback(),
		},
		update_modified=False,
	)
	frappe.db.commit()


def _quote_identifier(value: str) -> str:
	return "`" + value.replace("`", "``") + "`"


def _db_value(value: Any) -> Any:
	if isinstance(value, (dict, list, tuple)):
		return json.dumps(value, separators=(",", ":"), default=str)
	return value


def _chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
	for offset in range(0, len(values), size):
		yield values[offset : offset + size]
