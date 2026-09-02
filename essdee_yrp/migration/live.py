"""Live, resumable Production API migration runner.

The source is read through a server-configured Frappe-15 subprocess bridge.
Target writes are DB-level batched upserts so historical documents retain their
source state without firing incomplete F16 workflow logic.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import subprocess
import tempfile
from collections.abc import Iterable, Mapping
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import frappe
from frappe.model import no_value_fields
from frappe.utils import cint, now_datetime
from frappe.utils.password import set_encrypted_password

from essdee_yrp.migration.engine import MigrationError, MigrationPlan, transform_document
from essdee_yrp.migration.config import (
	MigrationSettings,
	get_migration_settings,
	is_target_reset_enabled,
)
from essdee_yrp.migration.planner import build_schema_analysis


SOURCE_BRIDGE = (
	Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"
)
DEFAULT_BATCH_SIZE = 250
MAX_SQL_PARAMETERS = 20_000
PROGRESS_UPDATE_INTERVAL = 10_000
RUNNING_STATUSES = {"Queued", "Running", "Analysing"}
TABLE_FIELD_TYPES = {"Table", "Table MultiSelect"}
NO_COLUMN_FIELD_TYPES = set(no_value_fields) - TABLE_FIELD_TYPES
SUPPORTING_EXTERNAL_DOCTYPE_ORDER = (
	"Role",
	"User",
	"Address",
	"Letter Head",
	"Email Account",
	"Print Format",
)
PRESERVE_SOURCE_BLANK_FIELDS = {
	# These fields are mandatory only in the F16 operating contract. Historical
	# source rows intentionally used blank to mean a global rate, a multi-Lot
	# header, or a movement created before warehouse capture. Dry Run audits the
	# exact source count; no creation-date guess is used in production.
	("Process Cost", "supplier"),
	("Process Cost", "lot"),
	("Purchase Order", "lot"),
	("Goods Received Note", "lot"),
	("Cut Panel Movement", "from_warehouse"),
	("Cutting Laysheet Planner", "description"),
}
SAFE_SQL_FIELDNAME = re.compile(r"^[a-z][a-z0-9_]*$")

# Migration operating context that must resolve before a Production Order or
# stock row is transformed. IPD Settings come from the F15 Single (with only
# reviewed F16-only profile defaults); stock settings define the target's live
# dimension contract. Keeping this here makes the contract independently
# auditable instead of silently inventing values in a transformer.
IPD_MIGRATION_PREREQUISITES = {
	"item_group": "Item Group",
	"default_cutting_process": "Process",
	"default_knitting_process": "Process",
	"default_dyeing_process": "Process",
	"default_packing_process": "Process",
	"default_pack_in_stage": "Item Attribute Value",
	"default_packing_attribute": "Item Attribute",
	"default_pack_out_stage": "Item Attribute Value",
	"default_stitching_process": "Process",
	"default_stitching_in_stage": "Item Attribute Value",
	"default_stitching_attribute": "Item Attribute",
	"default_stitching_out_stage": "Item Attribute Value",
	"default_set_item_attribute": "Item Attribute",
}
STOCK_MIGRATION_PREREQUISITES = {
	"transit_warehouse": "Warehouse",
	"default_received_type": "Received Type",
	"default_rejected_received_type": "Received Type",
}
REQUIRED_STOCK_DIMENSION_CONTRACT = {
	"lot": {
		"dimension_doctype": "Lot",
		"mandatory": 1,
		"in_valuation": 1,
		"is_production_group": 1,
	},
	"received_type": {
		"dimension_doctype": "Received Type",
		"mandatory": 1,
		"in_valuation": 1,
		"is_production_group": 0,
	},
}


class F15SourceBridge:
	def __init__(self, settings: MigrationSettings | None = None):
		self.settings = settings or get_migration_settings()

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
			"migration_defaults": dict(self.settings.required_defaults),
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
			elif kind == "migration_defaults":
				data["migration_defaults"].update(
					{
						"default_received_type": row.get("default_received_type"),
						"root_item_groups": row.get("root_item_groups") or [],
						"bill_received_via": row.get("bill_received_via") or [],
					}
				)
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
		return self.stock_summary_for_dimensions(_target_stock_dimension_fieldnames())

	def stock_summary_for_dimensions(self, dimensions: Iterable[str]) -> dict[str, Any]:
		lines = list(
			self._run(
				[
					"stock-summary",
					"--dimensions-json",
					json.dumps(list(dimensions), separators=(",", ":")),
				]
			)
		)
		if len(lines) != 1:
			raise MigrationError("F15 source bridge returned invalid stock summary")
		return lines[0]

	def iter_broken_links(self) -> Iterable[dict[str, Any]]:
		yield from self._run(["broken-links"])

	def document_exists(self, doctype: str, name: str) -> bool:
		lines = list(self._run(["exists", "--doctype", doctype, "--name", name]))
		if len(lines) != 1:
			raise MigrationError("F15 source bridge returned an invalid exists payload")
		return bool(lines[0].get("exists"))

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
		if not self.settings.source_python.is_file() or not SOURCE_BRIDGE.is_file():
			raise MigrationError("The configured F15 source bridge is not installed")
		connection_args = [
			"--source-bench",
			str(self.settings.source_bench),
			"--source-site",
			self.settings.source_site,
			"--source-app",
			self.settings.source_app,
		]
		with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr:
			process = subprocess.Popen(
				[
					str(self.settings.source_python),
					str(SOURCE_BRIDGE),
					*connection_args,
					*args,
				],
				cwd=self.settings.source_bench,
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
		blob = None
		for candidate in frappe.get_all(
			"File",
			filters={
				"content_hash": row.get("content_hash"),
				"is_private": int(row.get("is_private") or 0),
			},
			fields=["name", "file_url"],
			order_by="name asc",
			limit_page_length=0,
		):
			# Metadata-only rows from an incomplete local backup are not usable
			# deduplication sources. Reuse only a blob that really exists.
			if frappe.get_doc("File", candidate.name).exists_on_disk():
				blob = candidate
				break
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


def build_live_schema_analysis(
	settings: MigrationSettings | None = None,
	source: F15SourceBridge | None = None,
) -> tuple[MigrationPlan, dict[str, Any]]:
	"""Build the plan from the configured source and live target dimensions."""

	settings = settings or get_migration_settings()
	_assert_target_site(settings)
	source = source or F15SourceBridge(settings)
	dimensions, stock_doctypes, operational_doctypes = _target_stock_contract()
	plan, payload = build_schema_analysis(
		source_schemas=source.schemas(),
		dimensions=dimensions,
		stock_doctypes=stock_doctypes,
		operational_doctypes=operational_doctypes,
		source_site=settings.source_site,
		target_site=settings.target_site,
	)
	target_prerequisites = _validate_target_migration_prerequisites(
		dimensions,
		plan=plan,
		source=source,
		required_defaults=settings.required_defaults,
	)
	payload.update(
		{
			"mode": "live-schema",
			"reads_site_data": True,
			"writes_site_data": False,
			"target_prerequisites": target_prerequisites,
		}
	)
	_validate_configured_default_contract(plan, settings, source)
	return plan, payload


def _validate_configured_default_contract(
	plan: MigrationPlan,
	settings: MigrationSettings,
	source: F15SourceBridge,
) -> None:
	"""Fail Analyse on misspelled or unresolved site-config defaults."""

	for key, value in settings.required_defaults.items():
		if (
			not isinstance(key, str)
			or "." not in key
			or value in (None, "")
			or isinstance(value, (Mapping, list, tuple, set))
		):
			raise MigrationError(f"Invalid configured migration default {key!r}")
		doctype, fieldname = key.rsplit(".", 1)
		schema = plan.target_schemas.get(doctype)
		field = next(
			(
				row
				for row in (schema or {}).get("fields") or []
				if row.get("fieldname") == fieldname
			),
			None,
		)
		if not field or field.get("fieldtype") in TABLE_FIELD_TYPES:
			raise MigrationError(f"Unknown configured migration default {key}")
		if field.get("fieldtype") == "Select":
			options = {
				option.strip()
				for option in str(field.get("options") or "").splitlines()
				if option.strip()
			}
			if str(value) not in options:
				raise MigrationError(
					f"Configured migration default {key}={value!r} is not a Select option"
				)
		if field.get("fieldtype") != "Link":
			continue
		link_doctype = str(field.get("options") or "")
		if not link_doctype:
			raise MigrationError(f"Configured Link default {key} has no target DocType")
		if frappe.db.exists("DocType", link_doctype) and frappe.db.exists(
			link_doctype, value
		):
			continue
		source_doctypes = [
			source_doctype
			for source_doctype, spec in plan.specs.items()
			if spec.target == link_doctype and not spec.is_child
		]
		if len(source_doctypes) != 1 or not source.document_exists(
			source_doctypes[0], str(value)
		):
			raise MigrationError(
				f"Configured migration default {key}={value!r} does not resolve "
				f"to {link_doctype} on the target or frozen source"
			)


def _target_stock_contract() -> tuple[list[dict[str, Any]], list[str], list[str]]:
	from yrp.stock.dimensions import (
		OPERATIONAL_DOCTYPES,
		STOCK_DOCTYPES,
		get_stock_dimensions,
	)

	dimensions = [dict(row) for row in get_stock_dimensions()]
	if not dimensions:
		raise MigrationError("YRP Stock Settings has no configured stock dimensions")
	for row in dimensions:
		fieldname = str(row.get("fieldname") or "")
		if not SAFE_SQL_FIELDNAME.fullmatch(fieldname):
			raise MigrationError(f"Unsafe configured stock dimension {fieldname!r}")
	return dimensions, list(STOCK_DOCTYPES), list(OPERATIONAL_DOCTYPES)


def _validate_target_migration_prerequisites(
	dimensions: Iterable[Mapping[str, Any]],
	*,
	plan: MigrationPlan | None = None,
	source: F15SourceBridge | None = None,
	required_defaults: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
	"""Validate migration operating context before any target write occurs.

	IPD Settings are source-owned historical settings.  A new target has no
	business configuration yet, so Analyse reads the F15 Single and applies only
	the reviewed profile defaults needed for F16-only fields.  Stock settings and
	the dimension contract remain target-owned setup, as they define the active
	F16 stock model.
	"""

	issues: list[str] = []
	values: dict[str, dict[str, Any]] = {"IPD Settings": {}, "YRP Stock Settings": {}}
	value_sources: dict[str, dict[str, str]] = {
		"IPD Settings": {},
		"YRP Stock Settings": {},
	}
	source_ipd_settings = _source_single_document(source, "IPD Settings")
	required_defaults = required_defaults or {}
	for doctype, fields in (
		("IPD Settings", IPD_MIGRATION_PREREQUISITES),
		("YRP Stock Settings", STOCK_MIGRATION_PREREQUISITES),
	):
		for fieldname, link_doctype in fields.items():
			target_value = frappe.db.get_single_value(doctype, fieldname)
			value, value_source = _migration_prerequisite_value(
				doctype,
				fieldname,
				target_value=target_value,
				source_ipd_settings=source_ipd_settings,
				required_defaults=required_defaults,
			)
			values[doctype][fieldname] = value
			value_sources[doctype][fieldname] = value_source
			if value in (None, ""):
				if doctype == "IPD Settings":
					issues.append(
						f"{doctype}.{fieldname} is required from the F15 source or "
						"essdee_yrp_migration.required_defaults"
					)
				else:
					issues.append(f"{doctype}.{fieldname} is required")
			elif not _target_or_source_prerequisite_exists(
				link_doctype, str(value), plan=plan, source=source
			):
				issues.append(
					f"{doctype}.{fieldname}={value!r} does not resolve to "
					f"{link_doctype} on the target or frozen source"
				)

	dimension_rows = {
		str(row.get("fieldname") or ""): dict(row) for row in dimensions
	}
	for fieldname, expected in REQUIRED_STOCK_DIMENSION_CONTRACT.items():
		row = dimension_rows.get(fieldname)
		if not row:
			issues.append(f"YRP Stock Settings.stock_dimensions is missing {fieldname!r}")
			continue
		for key, expected_value in expected.items():
			actual = row.get(key)
			if key != "dimension_doctype":
				actual = cint(actual)
			if actual != expected_value:
				issues.append(
					"YRP Stock Settings.stock_dimensions "
					f"{fieldname!r} requires {key}={expected_value!r}; found {actual!r}"
				)

	if issues:
		raise MigrationError(
			"Migration target settings are incomplete:\n- " + "\n- ".join(issues)
		)

	return {
		"ipd_settings": values["IPD Settings"],
		"ipd_settings_sources": value_sources["IPD Settings"],
		"stock_settings": values["YRP Stock Settings"],
		"stock_dimensions": [
			{
				key: row.get(key)
				for key in (
					"dimension_doctype",
					"fieldname",
					"label",
					"mandatory",
					"in_valuation",
					"is_production_group",
				)
			}
			for row in dimensions
		],
	}


def _source_single_document(
	source: F15SourceBridge | None, doctype: str
) -> dict[str, Any] | None:
	"""Read one source Single without writing or relying on target state."""

	if source is None or not callable(getattr(source, "iter_documents", None)):
		return None
	documents = list(source.iter_documents(doctype, limit=2))
	if len(documents) != 1:
		raise MigrationError(
			f"F15 source must return exactly one {doctype}; found {len(documents)}"
		)
	document = dict(documents[0])
	if document.get("doctype") != doctype or document.get("name") != doctype:
		raise MigrationError(f"F15 source returned an invalid {doctype} Single")
	return document


def _migration_prerequisite_value(
	doctype: str,
	fieldname: str,
	*,
	target_value: Any,
	source_ipd_settings: Mapping[str, Any] | None,
	required_defaults: Mapping[str, Any],
) -> tuple[Any, str]:
	"""Return the source/profile value for source-owned IPD settings."""

	if doctype != "IPD Settings" or source_ipd_settings is None:
		return target_value, "target"
	source_value = source_ipd_settings.get(fieldname)
	if source_value not in (None, ""):
		return source_value, "production_api"
	configured_value = required_defaults.get(f"{doctype}.{fieldname}")
	if configured_value not in (None, ""):
		return configured_value, "migration_profile"
	return None, "missing"


def _target_or_source_prerequisite_exists(
	link_doctype: str,
	value: str,
	*,
	plan: MigrationPlan | None,
	source: F15SourceBridge | None,
) -> bool:
	if frappe.db.exists("DocType", link_doctype) and frappe.db.exists(
		link_doctype, value
	):
		return True
	if not plan or not source:
		return False
	source_doctypes = [
		source_doctype
		for source_doctype, spec in plan.specs.items()
		if spec.target == link_doctype and not spec.is_child
	]
	# Target Warehouse rows are deterministically generated from source Supplier
	# identities. They are intentionally absent during the clean reset boundary.
	if link_doctype == "Warehouse":
		source_doctypes.append("Supplier")
	return any(
		source.document_exists(source_doctype, value)
		for source_doctype in sorted(set(source_doctypes))
	)


def _target_stock_dimension_fieldnames() -> list[str]:
	return [str(row["fieldname"]) for row in _target_stock_contract()[0]]


def _assert_target_site(settings: MigrationSettings) -> None:
	if frappe.local.site != settings.target_site:
		raise MigrationError(
			f"Migration target changed from {settings.target_site} to {frappe.local.site}"
		)


def _source_snapshot(
	settings: MigrationSettings,
	status: Mapping[str, Any],
	broken_links: list[dict[str, Any]],
	plan: MigrationPlan,
	target_prerequisites: Mapping[str, Any],
) -> dict[str, Any]:
	broken_link_payload = json.dumps(
		broken_links, sort_keys=True, separators=(",", ":"), default=str
	)
	return {
		**settings.public_dict(),
		"snapshot_fingerprint": status.get("snapshot_fingerprint"),
		"total_parent_records": int(status.get("total_parent_records") or 0),
		"source_broken_link_count": len(broken_links),
		"source_broken_link_digest": hashlib.sha256(
			broken_link_payload.encode("utf-8")
		).hexdigest(),
		"migration_contract_fingerprint": _migration_contract_fingerprint(
			settings, plan
		),
		"target_prerequisite_fingerprint": hashlib.sha256(
			json.dumps(
				target_prerequisites,
				sort_keys=True,
				separators=(",", ":"),
				default=str,
			).encode("utf-8")
		).hexdigest(),
	}


def _migration_contract_fingerprint(
	settings: MigrationSettings, plan: MigrationPlan
) -> str:
	"""Bind the gate to deployed code, target schema, mappings, and defaults."""

	migration_root = Path(__file__).resolve().parent
	code_paths = [
		migration_root / name
		for name in (
			"config.py",
			"engine.py",
			"live.py",
			"planner.py",
			"rules.py",
			"schema.py",
			"transformers.py",
		)
	]
	code_paths.append(SOURCE_BRIDGE)
	code_paths.append(
		migration_root.parent
		/ "patches"
		/ "backfill_deterministic_valuation_lineage.py"
	)
	code_digest = hashlib.sha256()
	for path in code_paths:
		code_digest.update(path.name.encode("utf-8"))
		code_digest.update(b"\0")
		code_digest.update(path.read_bytes())
		code_digest.update(b"\0")
	contract = {
		"code_digest": code_digest.hexdigest(),
		"required_defaults": dict(settings.required_defaults),
		"target_schemas": plan.target_schemas,
		"specs": {
			source_doctype: {
				"target": spec.target,
				"kind": spec.kind,
				"field_map": dict(spec.field_map),
				"table_option_map": dict(spec.table_option_map),
				"ignored_fields": dict(spec.ignored_fields),
				"value_transformers": dict(spec.value_transformers),
				"custom_transformer": spec.custom_transformer,
				"post_transformer": spec.post_transformer,
			}
			for source_doctype, spec in sorted(plan.specs.items())
		},
	}
	payload = json.dumps(contract, sort_keys=True, separators=(",", ":"), default=str)
	return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _source_broken_link_manifest(
	plan: MigrationPlan,
	source: F15SourceBridge,
) -> list[dict[str, Any]]:
	"""Map exact source-invalid Link rows into their target field contract."""

	manifest: list[dict[str, Any]] = []
	for row in source.iter_broken_links():
		source_doctype = str(row.get("source_doctype") or "")
		spec = plan.specs.get(source_doctype)
		if not spec:
			raise MigrationError(f"Broken-link audit found unmapped {source_doctype}")
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
		if not target_field or target_field.get("fieldtype") != "Link":
			continue
		manifest.append(
			{
				"target_doctype": spec.target,
				"target_name": str(row.get("source_name") or ""),
				"target_field": target_fieldname,
				"target_link_doctype": str(target_field.get("options") or ""),
				"value": row.get("value"),
			}
		)
		if len(manifest) > 10_000:
			raise MigrationError(
				"Source contains more than 10,000 broken Links; clean or separately approve it"
			)
	return sorted(
		manifest,
		key=lambda row: (
			row["target_doctype"],
			row["target_field"],
			row["target_name"],
			str(row["value"]),
		),
	)


def _require_previous_snapshot(
	migration,
	mode: str,
	current_snapshot: Mapping[str, Any],
) -> None:
	if mode not in {"reset", "migrate", "verify"}:
		return
	try:
		previous_report = json.loads(migration.report_json or "{}")
	except (TypeError, ValueError) as exc:
		raise MigrationError("Previous migration report is not valid JSON") from exc
	previous_snapshot = previous_report.get("source_snapshot") or {}
	if not previous_snapshot:
		raise MigrationError(
			"A completed Dry Run from this production source is required before migration"
		)
	if dict(previous_snapshot) != dict(current_snapshot):
		raise MigrationError(
			"Source data/configuration changed after the previous migration gate; "
			"run Analyse and Dry Run again"
		)


def _assert_no_other_active_migration(migration_name: str) -> None:
	active = frappe.get_all(
		"MRP Data Migration",
		filters={
			"name": ["!=", migration_name],
			"status": ["in", sorted(RUNNING_STATUSES)],
		},
		pluck="name",
		limit=1,
	)
	if active:
		raise MigrationError(f"Another migration run is active: {active[0]}")


def run_job(
	migration_name: str,
	mode: str,
	batch_size: int = DEFAULT_BATCH_SIZE,
	allow_missing_files: bool = False,
):
	"""Run one action synchronously; callers normally enqueue this on ``long``."""

	settings = get_migration_settings()
	_assert_target_site(settings)
	if mode not in {"dry_run", "migrate", "verify"}:
		raise MigrationError(f"Unsupported migration mode {mode!r}")
	_assert_no_other_active_migration(migration_name)

	migration = frappe.get_doc("MRP Data Migration", migration_name)
	source = F15SourceBridge(settings)
	plan, schema_payload = build_live_schema_analysis(settings, source)
	if not plan.ready:
		raise MigrationError("Schema plan is blocked:\n" + "\n".join(plan.issues))
	_validate_live_target_metadata(plan)
	source_status = source.status()
	if source_status.get("site") != settings.source_site:
		raise MigrationError("The source bridge did not connect to the approved source site")
	broken_links = _source_broken_link_manifest(plan, source)
	snapshot = _source_snapshot(
		settings,
		source_status,
		broken_links,
		plan,
		schema_payload["target_prerequisites"],
	)
	_require_previous_snapshot(migration, mode, snapshot)
	if mode == "migrate" and not source_status.get("maintenance_mode"):
		raise MigrationError(
			f"{settings.source_site} must be in maintenance mode before the write migration starts"
		)
	_mark_started(migration_name, mode, source_status)
	try:
		if mode == "verify":
			result = _verify_counts(
				plan,
				source_status,
				source,
				migration_name,
				source_broken_links=broken_links,
			)
			result["source_snapshot"] = snapshot
			result["source_broken_links"] = broken_links
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
		if mode == "migrate":
			# Framework patches run before legacy source documents are loaded and
			# their Patch Log entries survive the migration-owned data reset. Run the
			# same conservative, idempotent backfill at the actual post-load boundary.
			from essdee_yrp.patches.backfill_deterministic_valuation_lineage import (
				backfill_deterministic_valuation_lineage,
			)

			result["valuation_lineage"] = backfill_deterministic_valuation_lineage()
		result["schema"] = {
			"source_doctypes": schema_payload["source_doctypes"],
			"target_doctypes": schema_payload["target_doctypes"],
			"migration_kinds": schema_payload["migration_kinds"],
		}
		result["source_snapshot"] = snapshot
		result["source_broken_links"] = broken_links
		_mark_complete(migration_name, mode, result)
		return result
	except Exception:
		_mark_failed(migration_name)
		raise


def enqueue_job(migration_name: str, mode: str, *, allow_missing_files: bool = False):
	return frappe.enqueue(
		"essdee_yrp.migration.live.run_job_guarded",
		queue="long",
		timeout=86_400,
		enqueue_after_commit=True,
		job_name=f"mrp-data-migration-{migration_name}-{mode}",
		migration_name=migration_name,
		mode=mode,
		allow_missing_files=bool(allow_missing_files),
	)


def enqueue_reset_job(migration_name: str):
	return frappe.enqueue(
		"essdee_yrp.migration.live.run_reset_job_guarded",
		queue="long",
		timeout=86_400,
		enqueue_after_commit=True,
		job_name=f"mrp-data-migration-{migration_name}-reset",
		migration_name=migration_name,
	)


def run_job_guarded(*args, **kwargs):
	"""Ensure a queued migration cannot stay Queued after preflight failure."""

	migration_name = str(kwargs.get("migration_name") or (args[0] if args else ""))
	try:
		return run_job(*args, **kwargs)
	except Exception:
		_mark_queued_failure(migration_name)
		raise


def run_reset_job_guarded(*args, **kwargs):
	"""Ensure a queued reset cannot stay Queued after preflight failure."""

	migration_name = str(kwargs.get("migration_name") or (args[0] if args else ""))
	try:
		return run_reset_job(*args, **kwargs)
	except Exception:
		_mark_queued_failure(migration_name)
		raise


def _mark_queued_failure(migration_name: str) -> None:
	if not migration_name:
		return
	status = frappe.db.get_value("MRP Data Migration", migration_name, "status")
	if status in RUNNING_STATUSES:
		_mark_failed(migration_name)


def preview_target_reset(migration_name: str) -> dict[str, Any]:
	"""Return the exact current deletion scope without mutating the target."""

	settings = get_migration_settings()
	_assert_target_site(settings)
	migration = frappe.get_doc("MRP Data Migration", migration_name)
	source = F15SourceBridge(settings)
	plan, schema_payload = build_live_schema_analysis(settings, source)
	source_status = source.status()
	broken_links = _source_broken_link_manifest(plan, source)
	snapshot = _source_snapshot(
		settings,
		source_status,
		broken_links,
		plan,
		schema_payload["target_prerequisites"],
	)
	_require_previous_snapshot(migration, "reset", snapshot)
	manifest = _build_target_reset_manifest(plan, source)
	counts = _include_reset_generated_audit_scope(
		migration, _target_reset_counts(manifest)
	)
	return {
		"target_site": settings.target_site,
		"source_site": settings.source_site,
		"source_maintenance_mode": bool(source_status.get("maintenance_mode")),
		"server_reset_enabled": is_target_reset_enabled(),
		"total_rows": counts["total"],
		"parent_rows": counts["parent_total"],
		"child_rows": counts["child_total"],
		"file_rows": counts["file_total"],
		"generated_supplier_warehouses": counts[
			"generated_supplier_warehouse_total"
		],
		"reset_generated_audit_rows": counts["reset_generated_audit_total"],
		"source_series_counters": len(manifest["source_series_names"]),
		"preserved_naming_series_counters": counts["preserved_series_total"],
		"parent_doctype_count": len(manifest["parent_target_doctypes"]),
		"child_doctype_count": len(manifest["child_target_doctypes"]),
		"preserved_single_doctypes": manifest["single_target_doctypes"],
	}


def run_reset_job(migration_name: str) -> dict[str, Any]:
	"""Delete only the reviewed migration-owned target graph before a fresh load."""

	settings = get_migration_settings()
	_assert_target_site(settings)
	if not is_target_reset_enabled():
		raise MigrationError(
			"Target reset is not enabled in server configuration. Isolate the target "
			"and set the one-time reset acknowledgement before retrying."
		)
	_assert_no_other_active_migration(migration_name)

	migration = frappe.get_doc("MRP Data Migration", migration_name)
	source = F15SourceBridge(settings)
	plan, schema_payload = build_live_schema_analysis(settings, source)
	if not plan.ready:
		raise MigrationError("Schema plan is blocked:\n" + "\n".join(plan.issues))
	_validate_live_target_metadata(plan)
	source_status = source.status()
	if source_status.get("site") != settings.source_site:
		raise MigrationError("The source bridge did not connect to the approved source site")
	broken_links = _source_broken_link_manifest(plan, source)
	snapshot = _source_snapshot(
		settings,
		source_status,
		broken_links,
		plan,
		schema_payload["target_prerequisites"],
	)
	_require_previous_snapshot(migration, "reset", snapshot)
	if not source_status.get("maintenance_mode"):
		raise MigrationError(
			f"{settings.source_site} must be in maintenance mode before target reset"
		)

	manifest = _build_target_reset_manifest(plan, source)
	before = _include_reset_generated_audit_scope(
		migration, _target_reset_counts(manifest)
	)
	before = _bind_reset_series_checkpoint(migration, before)
	_mark_reset_started(migration_name, before)
	try:
		_delete_target_reset_manifest(migration_name, manifest, before)
		after = _include_reset_generated_audit_scope(
			migration,
			_target_reset_counts(manifest, expected_identities=before),
		)
		remaining = _nonzero_reset_counts(after)
		if remaining:
			raise MigrationError(
				"Target reset left migration-owned rows:\n"
				+ "\n".join(f"{key}: {value}" for key, value in remaining.items())
			)
		# Re-evaluate values and stock-dimension children after every destructive
		# table operation. Link masters may correctly be absent at this boundary;
		# they must still resolve from the frozen source graph.
		dimensions, _stock_doctypes, _operational_doctypes = _target_stock_contract()
		preserved_prerequisites = _validate_target_migration_prerequisites(
			dimensions, plan=plan, source=source
		)
		result = {
			"mode": "reset",
			"processed": before["total"],
			"skipped": 0,
			"failed": 0,
			"before": before,
			"after": after,
			"preserved_single_doctypes": manifest["single_target_doctypes"],
			"preserved_target_prerequisites": preserved_prerequisites,
			"source_snapshot": snapshot,
			"source_broken_links": broken_links,
		}
		_mark_reset_complete(migration_name, result)
		frappe.clear_cache()
		return result
	except Exception:
		_mark_failed(migration_name)
		raise


def _build_target_reset_manifest(
	plan: MigrationPlan,
	source: F15SourceBridge,
) -> dict[str, Any]:
	parent_targets = sorted(
		{
			spec.target
			for spec in plan.specs.values()
			if not spec.is_child and not spec.source_schema.get("issingle")
		}
	)
	single_targets = sorted(
		{
			spec.target
			for spec in plan.specs.values()
			if not spec.is_child and spec.source_schema.get("issingle")
		}
	)
	# A parent rule can contextually redirect a source child table to a different
	# target child DocType (for example Item Production Detail.item_attributes
	# maps Item Item Attribute to IPD Item Attribute).  That contextual target is
	# not necessarily the direct target of any child spec, so collecting only
	# ``spec.is_child`` targets leaves old rows behind when their parent no longer
	# exists in the source.  Include every physical table referenced by a
	# migration-owned target parent; deletion remains scoped by parenttype below.
	child_targets = {
		spec.target for spec in plan.specs.values() if spec.is_child
	}
	for parent_target in parent_targets:
		for field in (getattr(plan, "target_schemas", {}).get(parent_target) or {}).get(
			"fields", []
		):
			if field.get("fieldtype") in TABLE_FIELD_TYPES and field.get("options"):
				child_targets.add(str(field["options"]))
	child_targets = sorted(child_targets)
	series_names = []
	for row in source.iter_series():
		name = str(row.get("name") or "")
		series_names.append(name)
	return {
		"parent_target_doctypes": parent_targets,
		"single_target_doctypes": single_targets,
		"child_target_doctypes": child_targets,
		"source_series_names": sorted(set(series_names)),
		"delete_generated_supplier_warehouses": "Supplier" in parent_targets,
	}


def _target_reset_counts(
	manifest: Mapping[str, Any],
	*,
	expected_identities: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
	parent_counts = {
		doctype: int(frappe.db.count(doctype))
		for doctype in manifest["parent_target_doctypes"]
	}
	parenttypes = list(manifest["parent_target_doctypes"])
	child_counts = {
		doctype: int(
			frappe.db.count(doctype, {"parenttype": ["in", parenttypes]})
			if parenttypes
			else 0
		)
		for doctype in manifest["child_target_doctypes"]
	}
	file_names = _target_reset_file_names(manifest)
	warehouse_names = _generated_supplier_warehouse_names(manifest)
	if expected_identities is None:
		preserved_series_values = _target_series_values()
		preserved_series_mismatches = []
	else:
		file_names = sorted(
			set(file_names)
			| set(
				_existing_document_names(
					"File", list(expected_identities.get("file_names") or [])
				)
			)
		)
		warehouse_names = sorted(
			set(warehouse_names)
			| set(
				_existing_document_names(
					"Warehouse",
					list(
						expected_identities.get(
							"generated_supplier_warehouse_names"
						)
						or []
					),
				)
			)
		)
		preserved_series_values = _target_series_values()
		expected_series_values = dict(
			expected_identities.get("preserved_series_values") or {}
		)
		preserved_series_mismatches = _series_value_mismatches(
			expected_series_values, preserved_series_values
		)
	total = (
		sum(parent_counts.values())
		+ sum(child_counts.values())
		+ len(file_names)
		+ len(warehouse_names)
	)
	return {
		"total": total,
		"parent_total": sum(parent_counts.values()),
		"child_total": sum(child_counts.values()),
		"file_total": len(file_names),
		"generated_supplier_warehouse_total": len(warehouse_names),
		"series_total": 0,
		"preserved_series_total": len(preserved_series_values),
		"preserved_series_mismatch_total": len(preserved_series_mismatches),
		"parent_counts": parent_counts,
		"child_counts": child_counts,
		"file_names": file_names,
		"generated_supplier_warehouse_names": warehouse_names,
		"preserved_series_values": preserved_series_values,
		"preserved_series_mismatches": preserved_series_mismatches,
	}


def _target_reset_file_names(manifest: Mapping[str, Any]) -> list[str]:
	parent_targets = list(manifest["parent_target_doctypes"])
	child_targets = list(manifest["child_target_doctypes"])
	attachment_targets = sorted(set(parent_targets + child_targets))
	if not attachment_targets:
		return []
	rows = frappe.get_all(
		"File",
		filters={"attached_to_doctype": ["in", attachment_targets]},
		fields=["name", "attached_to_doctype", "attached_to_name"],
		order_by="name asc",
		limit_page_length=0,
	)
	child_names: dict[str, set[str]] = {}
	for doctype in child_targets:
		attached_names = sorted(
			{
				str(row.attached_to_name)
				for row in rows
				if row.attached_to_doctype == doctype and row.attached_to_name
			}
		)
		child_names[doctype] = set()
		for chunk in _chunks(attached_names, 500):
			child_names[doctype].update(
				frappe.get_all(
					doctype,
					filters={
						"name": ["in", chunk],
						"parenttype": ["in", parent_targets],
					},
					pluck="name",
					limit_page_length=0,
				)
			)
	return [
		str(row.name)
		for row in rows
		if row.attached_to_doctype in parent_targets
		or str(row.attached_to_name or "")
		in child_names.get(str(row.attached_to_doctype), set())
	]


def _generated_supplier_warehouse_names(manifest: Mapping[str, Any]) -> list[str]:
	if not manifest["delete_generated_supplier_warehouses"]:
		return []
	return [
		str(row[0])
		for row in frappe.db.sql(
			"SELECT warehouse.name FROM `tabWarehouse` warehouse "
			"WHERE COALESCE(warehouse.supplier, '')<>'' "
			"AND warehouse.name=warehouse.supplier ORDER BY warehouse.name"
		)
	]


def _target_series_values() -> dict[str, int]:
	"""Snapshot every target naming counter, including the blank identity."""

	return {
		str(name or ""): int(current or 0)
		for name, current in frappe.db.sql(
			"SELECT `name`, `current` FROM `tabSeries` ORDER BY `name`"
		)
	}


def _series_value_mismatches(
	expected: Mapping[str, Any],
	actual: Mapping[str, Any],
) -> list[dict[str, Any]]:
	missing = object()
	mismatches = []
	for name in sorted(set(expected) | set(actual)):
		expected_value = expected.get(name, missing)
		actual_value = actual.get(name, missing)
		if expected_value == actual_value:
			continue
		mismatches.append(
			{
				"name": name,
				"expected": None if expected_value is missing else int(expected_value),
				"actual": None if actual_value is missing else int(actual_value),
			}
		)
	return mismatches


def _bind_reset_series_checkpoint(
	migration: Any,
	before: Mapping[str, Any],
) -> dict[str, Any]:
	"""Keep the first reset attempt's complete series snapshot across retries."""

	checkpoint = {}
	if migration.checkpoint_json:
		try:
			checkpoint = json.loads(migration.checkpoint_json)
		except (TypeError, ValueError) as exc:
			raise MigrationError("Reset checkpoint JSON is invalid") from exc
		if checkpoint and checkpoint.get("mode") != "reset":
			raise MigrationError("The migration contains a non-reset checkpoint")

	expected = dict(
		checkpoint.get("preserved_series_values")
		or before.get("preserved_series_values")
		or {}
	)
	actual = dict(before.get("preserved_series_values") or {})
	mismatches = _series_value_mismatches(expected, actual)
	if mismatches:
		raise MigrationError(
			"Naming-series counters changed after the first reset attempt; "
			"restore or review the preserved reset checkpoint before retrying:\n"
			+ "\n".join(
				f"{row['name']!r}: expected={row['expected']}, actual={row['actual']}"
				for row in mismatches[:100]
			)
		)

	bound = dict(before)
	bound["preserved_series_values"] = expected
	bound["preserved_series_total"] = len(expected)
	bound["preserved_series_mismatch_total"] = 0
	bound["preserved_series_mismatches"] = []
	bound["reset_started_on"] = checkpoint.get("reset_started_on")
	return bound


def _include_reset_generated_audit_scope(
	migration: Any,
	counts: Mapping[str, Any],
) -> dict[str, Any]:
	"""Include only exact audit identities already owned by this reset."""

	checkpoint = {}
	if migration.checkpoint_json:
		try:
			checkpoint = json.loads(migration.checkpoint_json)
		except (TypeError, ValueError) as exc:
			raise MigrationError("Reset checkpoint JSON is invalid") from exc
	deleted_document_names = []
	comment_names = []
	if checkpoint.get("mode") == "reset":
		deleted_document_names = _existing_document_names(
			"Deleted Document",
			list(checkpoint.get("reset_generated_deleted_document_names") or []),
		)
		comment_names = _existing_document_names(
			"Comment",
			list(checkpoint.get("reset_generated_comment_names") or []),
		)
	result = dict(counts)
	result["reset_generated_deleted_document_names"] = list(deleted_document_names)
	result["reset_generated_deleted_document_total"] = len(deleted_document_names)
	result["reset_generated_comment_names"] = list(comment_names)
	result["reset_generated_comment_total"] = len(comment_names)
	result["reset_generated_audit_total"] = len(deleted_document_names) + len(
		comment_names
	)
	result["total"] = int(result.get("total") or 0) + result[
		"reset_generated_audit_total"
	]
	return result


def _existing_document_names(doctype: str, names: list[str]) -> list[str]:
	existing = []
	for chunk in _chunks(names, 500):
		existing.extend(
			str(name)
			for name in frappe.get_all(
				doctype,
				filters={"name": ["in", chunk]},
				pluck="name",
				limit_page_length=0,
			)
		)
	return sorted(existing)


def _delete_target_reset_manifest(
	migration_name: str,
	manifest: Mapping[str, Any],
	before: Mapping[str, Any],
) -> None:
	processed = 0
	for chunk in _chunks(
		list(before.get("reset_generated_deleted_document_names") or []), 500
	):
		frappe.db.delete("Deleted Document", {"name": ["in", chunk]})
		frappe.db.commit()
		processed += len(chunk)
		_update_progress(migration_name, processed, 0, 0)
	for chunk in _chunks(
		list(before.get("reset_generated_comment_names") or []), 500
	):
		frappe.db.delete("Comment", {"name": ["in", chunk]})
		frappe.db.commit()
		processed += len(chunk)
		_update_progress(migration_name, processed, 0, 0)

	for chunk in _chunks(list(before["file_names"]), 50):
		for name in chunk:
			_delete_reset_file(name)
			frappe.db.commit()
			processed += 1
			_update_progress(migration_name, processed, 0, 0)

	warehouse_names = list(before["generated_supplier_warehouse_names"])
	for chunk in _chunks(warehouse_names, 500):
		frappe.db.delete("Warehouse", {"name": ["in", chunk]})
		frappe.db.commit()
		processed += len(chunk)
		_update_progress(migration_name, processed, 0, 0)

	parenttypes = list(manifest["parent_target_doctypes"])
	for doctype in manifest["child_target_doctypes"]:
		count = int(before["child_counts"].get(doctype) or 0)
		if count:
			frappe.db.delete(doctype, {"parenttype": ["in", parenttypes]})
			frappe.db.commit()
		processed += count
		_update_progress(migration_name, processed, 0, 0)

	for doctype in manifest["parent_target_doctypes"]:
		count = int(before["parent_counts"].get(doctype) or 0)
		if count:
			frappe.db.delete(doctype)
			frappe.db.commit()
		processed += count
		_update_progress(migration_name, processed, 0, 0)


def _delete_reset_file(name: str) -> None:
	"""Run physical File cleanup without creating one queued job per row."""

	from frappe.model.delete_doc import delete_dynamic_links

	doc = frappe.get_doc("File", name)
	doc.validate_protected_file()
	doc._delete_file_on_disk()
	frappe.delete_doc(
		"File",
		name,
		ignore_permissions=True,
		force=True,
		for_reload=True,
		delete_permanently=True,
	)
	delete_dynamic_links("File", name)


def _nonzero_reset_counts(counts: Mapping[str, Any]) -> dict[str, int]:
	return {
		key: int(counts.get(key) or 0)
		for key in (
			"parent_total",
			"child_total",
			"file_total",
			"generated_supplier_warehouse_total",
			"reset_generated_deleted_document_total",
			"reset_generated_comment_total",
			"series_total",
			"preserved_series_mismatch_total",
		)
		if int(counts.get(key) or 0)
	}


def run_value_verification(
	migration_name: str,
	batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
	"""Run only the read-only exact-value layer for focused diagnostics."""

	settings = get_migration_settings()
	_assert_target_site(settings)
	if not frappe.db.exists("MRP Data Migration", migration_name):
		raise MigrationError(f"Unknown MRP Data Migration {migration_name}")
	source = F15SourceBridge(settings)
	plan, _schema_payload = build_live_schema_analysis(settings, source)
	if not plan.ready:
		raise MigrationError("Schema plan is blocked:\n" + "\n".join(plan.issues))
	_validate_live_target_metadata(plan)
	return _verify_source_values(
		plan,
		source,
		migration_name,
		batch_size=max(1, min(int(batch_size), 1000)),
	)


def run_attachment_smoke_test(source_file_names: Iterable[str]) -> dict[str, Any]:
	"""Migrate and verify selected source files without starting the full load.

	This diagnostic uses the same F15 bridge and target File lifecycle as the
	production migration. The matching parent documents must already exist on
	the target so the test cannot accidentally pull unrelated business data.
	"""

	settings = get_migration_settings()
	_assert_target_site(settings)
	names = sorted({str(name) for name in source_file_names if name})
	if not names:
		raise MigrationError("Attachment smoke test needs at least one File name")

	source = F15SourceBridge(settings)
	plan, _schema_payload = build_live_schema_analysis(settings, source)
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
		"source_site": settings.source_site,
		"target_site": settings.target_site,
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
		_ensure_supporting_masters(target, reference_data)
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
	if status.get("site") != source.settings.source_site:
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
	orphan_attachment_count = 0
	orphan_attachment_bytes = 0

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
			is_orphan = bool(row.get("orphan_attachment"))
			if is_orphan:
				orphan_attachment_count += 1
				orphan_attachment_bytes += int(row.get("file_size") or 0)
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
					if not is_orphan:
						target.upsert_missing_file_metadata(row, plan)
					file_state = checkpoint.setdefault("files", {})
					file_state["last_name"] = row["name"]
					file_state["processed"] = int(file_state.get("processed") or 0) + 1
					bucket = "orphan_attachment_names" if is_orphan else "missing_blob_names"
					bucket_names = set(file_state.get(bucket) or [])
					bucket_names.add(row["name"])
					file_state[bucket] = sorted(bucket_names)
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
				if not is_orphan:
					outcome = target.upsert_file(row, plan)
					if outcome["status"] in {"created", "repaired"}:
						created += 1
					else:
						existing += 1
				file_state = checkpoint.setdefault("files", {})
				file_state["last_name"] = row["name"]
				file_state["processed"] = int(file_state.get("processed") or 0) + 1
				if is_orphan:
					orphan_names = set(file_state.get("orphan_attachment_names") or [])
					orphan_names.add(row["name"])
					file_state["orphan_attachment_names"] = sorted(orphan_names)
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
		"orphan_attachment_count": orphan_attachment_count,
		"orphan_attachment_bytes": orphan_attachment_bytes,
		"orphan_attachment_policy": "Audited Source Orphan Omission",
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
	_apply_contextual_defaults(document, target_schema, reference_data)
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


def _apply_contextual_defaults(
	document: dict[str, Any],
	target_schema: Mapping[str, Any],
	reference_data: Mapping[str, Mapping[str, Any]] | None,
) -> None:
	"""Apply source/config-derived defaults to optional and mandatory fields."""

	reference_data = reference_data or {}
	defaults = reference_data.get("migration_defaults", {})
	fieldnames = {
		str(field.get("fieldname"))
		for field in target_schema.get("fields") or []
		if field.get("fieldname")
	}
	for fieldname in fieldnames:
		if document.get(fieldname) not in (None, ""):
			continue
		configured_value = defaults.get(f"{document.get('doctype')}.{fieldname}")
		if configured_value not in (None, ""):
			document[fieldname] = configured_value
	if "received_type" in fieldnames and not document.get("received_type"):
		default_received_type = defaults.get("default_received_type")
		if default_received_type:
			document["received_type"] = default_received_type


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
	if document.get("doctype") == "Item" and fieldname == "item_group":
		# Production API contains legacy Items created before Item Group became
		# mandatory.  The live SD-YRP consumer already uses the root group for
		# this exact compatibility case; apply the same deterministic mapping to
		# the historical query migration without changing any nonblank value.
		return _one_source_root_item_group(reference_data)
	if fieldname == "received_type":
		# Use the source Stock Settings value. Legacy rows often omitted the
		# explicit bucket; nonblank rejection/mistake types pass through untouched.
		return reference_data.get("migration_defaults", {}).get(
			"default_received_type"
		)
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
			source_groups = reference_data.get("item_groups", {})
			if str(item) in source_groups:
				# The PI row and its source Item can both predate mandatory
				# Item Group. Keep this aligned with the legacy Item mapping.
				return source_groups[str(item)] or _one_source_root_item_group(
					reference_data
				)
			return frappe.db.get_value("Item", item, "item_group")
	return None


def _is_valid_historical_required_blank(
	document: Mapping[str, Any], fieldname: str
) -> bool:
	return (str(document.get("doctype")), fieldname) in PRESERVE_SOURCE_BLANK_FIELDS


def _one_source_root_item_group(
	reference_data: Mapping[str, Mapping[str, Any]] | None,
) -> str | None:
	values = list(
		(reference_data or {}).get("migration_defaults", {}).get("root_item_groups")
		or []
	)
	if len(values) == 1:
		return str(values[0])
	if values:
		raise MigrationError(
			"Source has several root Item Groups; configure one unambiguous migration root"
		)
	return None


def _ensure_supporting_masters(
	target: FrappeBulkTarget,
	reference_data: Mapping[str, Mapping[str, Any]],
) -> None:
	now = now_datetime()
	defaults = reference_data.get("migration_defaults", {})
	received_via_values = sorted(
		{str(value) for value in defaults.get("bill_received_via") or [] if value}
	)
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
			for name in received_via_values
		],
	)
	default_received_type = defaults.get("default_received_type")
	if default_received_type and not frappe.db.exists(
		"Received Type", default_received_type
	):
		# The actual ten source records are migrated through GRN Item Type. This
		# early row only satisfies dependency checks if another DocType sorts first.
		target._bulk_upsert(
			"Received Type",
			[
				{
					"name": default_received_type,
					"received_type_name": default_received_type,
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
	*,
	source_broken_links: list[dict[str, Any]],
) -> dict[str, Any]:
	identity = _verify_source_identities(plan, source, migration_name)
	values = _verify_source_values(plan, source, migration_name)
	checkpoint = _load_checkpoint(migration_name)
	missing_blob_names = set(
		(checkpoint.get("files") or {}).get("missing_blob_names") or []
	)
	files = _verify_files(plan, source, allowed_missing_blob_names=missing_blob_names)
	series = _verify_series(source)
	stock = _verify_stock_summary(source)
	links = _verify_link_integrity(plan, source_broken_links)
	failures = [
		*identity["failures"],
		*values["failures"],
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
		"values": values,
		"files": files,
		"series": series,
		"stock": stock,
		"links": links,
	}


def _verify_source_values(
	plan: MigrationPlan,
	source: F15SourceBridge,
	migration_name: str,
	batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, Any]:
	"""Compare every transformed source value with its stored target value.

	The verifier is query-only. It uses the same reviewed mapping and required-
	value rules as the writer, batches target SELECTs by identity, and includes
	all recursively transformed child rows. Passwords are deliberately excluded
	because the target re-encrypts them with its own site key.
	"""

	reference_data = source.reference_data()
	columns_cache: dict[str, set[str]] = {}
	fieldtypes_cache: dict[str, dict[str, str]] = {}
	numeric_scales_cache: dict[str, dict[str, int]] = {}
	failures: list[str] = []
	doctype_rows: list[dict[str, Any]] = []
	verified_parents = 0
	last_progress_update = 0
	verified_documents = 0
	verified_values = 0
	skipped_password_values = 0
	normalized_attachment_urls: list[str] = []
	normalized_numeric_values: list[str] = []
	historical_required_blanks: dict[str, int] = {}

	for source_doctype in plan.parent_doctypes:
		effective_batch_size = max(1, min(int(batch_size), 1000))
		batch: list[dict[str, Any]] = []
		doctype_documents = 0
		doctype_values = 0
		doctype_passwords = 0
		doctype_attachment_urls = 0
		doctype_numeric_values = 0
		for source_document in source.iter_documents(
			source_doctype, batch_size=effective_batch_size
		):
			target_document = transform_document(source_document, plan)
			_resolve_and_validate_required_target_values(
				target_document,
				plan,
				historical_required_blanks,
				reference_data,
			)
			batch.append(target_document)
			verified_parents += 1
			if len(batch) < effective_batch_size:
				continue
			result = _verify_transformed_value_batch(
				batch,
				plan,
				columns_cache=columns_cache,
				fieldtypes_cache=fieldtypes_cache,
				numeric_scales_cache=numeric_scales_cache,
			)
			doctype_documents += result["documents"]
			doctype_values += result["values"]
			doctype_passwords += result["skipped_password_values"]
			doctype_attachment_urls += len(result["normalized_attachment_urls"])
			normalized_attachment_urls.extend(result["normalized_attachment_urls"])
			doctype_numeric_values += len(result["normalized_numeric_values"])
			normalized_numeric_values.extend(result["normalized_numeric_values"])
			failures.extend(result["failures"][: max(0, 100 - len(failures))])
			batch = []
			if failures:
				break
			if verified_parents - last_progress_update >= PROGRESS_UPDATE_INTERVAL:
				_update_progress(migration_name, verified_parents, 0, 0)
				last_progress_update = verified_parents
		if batch and not failures:
			result = _verify_transformed_value_batch(
				batch,
				plan,
				columns_cache=columns_cache,
				fieldtypes_cache=fieldtypes_cache,
				numeric_scales_cache=numeric_scales_cache,
			)
			doctype_documents += result["documents"]
			doctype_values += result["values"]
			doctype_passwords += result["skipped_password_values"]
			doctype_attachment_urls += len(result["normalized_attachment_urls"])
			normalized_attachment_urls.extend(result["normalized_attachment_urls"])
			doctype_numeric_values += len(result["normalized_numeric_values"])
			normalized_numeric_values.extend(result["normalized_numeric_values"])
			failures.extend(result["failures"][: max(0, 100 - len(failures))])

		verified_documents += doctype_documents
		verified_values += doctype_values
		skipped_password_values += doctype_passwords
		doctype_rows.append(
			{
				"source_doctype": source_doctype,
				"target_doctype": plan.specs[source_doctype].target,
				"verified_documents": doctype_documents,
				"verified_values": doctype_values,
				"skipped_password_values": doctype_passwords,
				"normalized_attachment_urls": doctype_attachment_urls,
				"normalized_numeric_values": doctype_numeric_values,
				"status": "Failed" if failures else "Pass",
			}
		)
		_update_progress(migration_name, verified_parents, 0, len(failures))
		last_progress_update = verified_parents
		if failures:
			break

	return {
		"status": "Pass" if not failures else "Failed",
		"verified_parent_records": verified_parents,
		"verified_parent_and_child_documents": verified_documents,
		"verified_field_values": verified_values,
		"skipped_password_values": skipped_password_values,
		"normalized_attachment_url_count": len(normalized_attachment_urls),
		"normalized_attachment_urls": normalized_attachment_urls,
		"normalized_numeric_value_count": len(normalized_numeric_values),
		"normalized_numeric_values": normalized_numeric_values[:100],
		"historical_required_blanks": historical_required_blanks,
		"doctypes": doctype_rows,
		"failures": failures,
	}


def _verify_transformed_value_batch(
	documents: list[dict[str, Any]],
	plan: MigrationPlan,
	*,
	columns_cache: dict[str, set[str]] | None = None,
	fieldtypes_cache: dict[str, dict[str, str]] | None = None,
	numeric_scales_cache: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
	columns_cache = columns_cache if columns_cache is not None else {}
	fieldtypes_cache = fieldtypes_cache if fieldtypes_cache is not None else {}
	numeric_scales_cache = (
		numeric_scales_cache if numeric_scales_cache is not None else {}
	)
	grouped: dict[str, list[dict[str, Any]]] = {}
	skipped_password_values = 0
	for document in documents:
		skipped_password_values += _collect_expected_value_rows(document, plan, grouped)

	verified_documents = 0
	verified_values = 0
	failures: list[str] = []
	normalized_attachment_urls: list[str] = []
	normalized_numeric_values: list[str] = []
	for doctype, expected_rows in grouped.items():
		schema = plan.target_schemas[doctype]
		if doctype not in fieldtypes_cache:
			fieldtypes_cache[doctype] = {
				str(field["fieldname"]): str(field.get("fieldtype") or "")
				for field in schema.get("fields") or []
				if field.get("fieldname")
			}
		fieldtypes = fieldtypes_cache[doctype]
		if schema.get("issingle"):
			actual_rows = frappe.db.sql(
				"SELECT `field`, `value` FROM `tabSingles` WHERE `doctype`=%s",
				(doctype,),
				as_dict=True,
			)
			actual: dict[str, Any] = {}
			for row in actual_rows:
				fieldname = str(row["field"])
				if fieldname in actual:
					failures.append(f"Duplicate Single value {doctype}.{fieldname}")
				actual[fieldname] = row["value"]
			for expected in expected_rows:
				verified_documents += 1
				for fieldname, expected_value in expected.items():
					if fieldname not in fieldtypes:
						continue
					if fieldname not in actual:
						failures.append(f"Missing Single value {doctype}.{fieldname}")
						continue
					if not _same_migrated_value(
						expected_value, actual[fieldname], fieldtypes.get(fieldname)
					):
						if _is_verified_attachment_url(
							doctype,
							doctype,
							fieldname,
							actual[fieldname],
							fieldtypes.get(fieldname),
						):
							normalized_attachment_urls.append(f"{doctype}.{fieldname}")
						else:
							failures.append(
								f"Value mismatch {doctype}.{fieldname}: "
								f"source={expected_value!r}, target={actual[fieldname]!r}"
							)
					verified_values += 1
					if len(failures) >= 100:
						break
				if len(failures) >= 100:
					break
			continue

		if doctype not in columns_cache:
			columns_cache[doctype] = set(frappe.db.get_table_columns(doctype))
		columns = columns_cache[doctype]
		if doctype not in numeric_scales_cache:
			numeric_scales_cache[doctype] = {
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
		numeric_scales = numeric_scales_cache[doctype]
		fields = sorted(
			{
				fieldname
				for expected in expected_rows
				for fieldname in expected
				if fieldname in columns
			}
		)
		if "name" not in fields:
			fields.insert(0, "name")
		names = [str(row["name"]) for row in expected_rows]
		actual_by_name: dict[str, dict[str, Any]] = {}
		for name_chunk in _chunks(list(dict.fromkeys(names)), 500):
			placeholders = ", ".join(["%s"] * len(name_chunk))
			selected = ", ".join(_quote_identifier(field) for field in fields)
			for row in frappe.db.sql(
				f"SELECT {selected} FROM {_quote_identifier('tab' + doctype)} "
				f"WHERE `name` IN ({placeholders})",
				name_chunk,
				as_dict=True,
			):
				actual_by_name[str(row["name"])] = row

		for expected in expected_rows:
			verified_documents += 1
			name = str(expected["name"])
			actual = actual_by_name.get(name)
			if actual is None:
				failures.append(f"Missing value-audit row {doctype} {name}")
				continue
			for fieldname, expected_value in expected.items():
				if fieldname not in columns:
					continue
				exact_value = _same_migrated_value(
					expected_value, actual.get(fieldname), fieldtypes.get(fieldname)
				)
				target_value = _same_migrated_value(
					expected_value,
					actual.get(fieldname),
					fieldtypes.get(fieldname),
					numeric_scale=numeric_scales.get(fieldname),
				)
				if target_value and not exact_value:
					normalized_numeric_values.append(f"{doctype} {name}.{fieldname}")
				elif not target_value:
					if _is_verified_attachment_url(
						doctype,
						name,
						fieldname,
						actual.get(fieldname),
						fieldtypes.get(fieldname),
					):
						normalized_attachment_urls.append(f"{doctype} {name}.{fieldname}")
					else:
						failures.append(
							f"Value mismatch {doctype} {name}.{fieldname}: "
							f"source={expected_value!r}, target={actual.get(fieldname)!r}"
						)
				verified_values += 1
				if len(failures) >= 100:
					break
			if len(failures) >= 100:
				break
		if failures:
			break

	return {
		"documents": verified_documents,
		"values": verified_values,
		"skipped_password_values": skipped_password_values,
		"normalized_attachment_urls": normalized_attachment_urls,
		"normalized_numeric_values": normalized_numeric_values,
		"failures": failures,
	}


def _collect_expected_value_rows(
	document: Mapping[str, Any],
	plan: MigrationPlan,
	grouped: dict[str, list[dict[str, Any]]],
	*,
	parent: Mapping[str, Any] | None = None,
) -> int:
	doctype = str(document["doctype"])
	schema = plan.target_schemas[doctype]
	table_fields = {
		str(field["fieldname"]): field
		for field in schema.get("fields") or []
		if field.get("fieldname") and field.get("fieldtype") in TABLE_FIELD_TYPES
	}
	row = {
		fieldname: value
		for fieldname, value in document.items()
		if fieldname not in table_fields
		and fieldname not in {"doctype", "__migration_passwords"}
	}
	if parent:
		row.update(parent)
	grouped.setdefault(doctype, []).append(row)
	skipped_password_values = len(document.get("__migration_passwords") or {})
	for fieldname, table_field in table_fields.items():
		if fieldname not in document:
			continue
		for idx, child in enumerate(document.get(fieldname) or [], start=1):
			skipped_password_values += _collect_expected_value_rows(
				child,
				plan,
				grouped,
				parent={
					"parent": document["name"],
					"parenttype": doctype,
					"parentfield": fieldname,
					"idx": idx,
				},
			)
	return skipped_password_values


def _same_migrated_value(
	expected: Any,
	actual: Any,
	fieldtype: str | None,
	*,
	numeric_scale: int | None = None,
) -> bool:
	expected = _db_value(expected)
	if expected is None or actual is None:
		return expected is None and actual is None
	if fieldtype in {"Check", "Currency", "Float", "Int", "Percent"}:
		try:
			expected_decimal = Decimal(str(expected or 0))
			actual_decimal = Decimal(str(actual or 0))
			if numeric_scale is not None:
				quantum = Decimal(1).scaleb(-numeric_scale)
				expected_decimal = expected_decimal.quantize(
					quantum, rounding=ROUND_HALF_UP
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
	if isinstance(expected, bytes):
		expected = expected.decode(errors="replace")
	if isinstance(actual, bytes):
		actual = actual.decode(errors="replace")
	if isinstance(expected, (date, datetime, time)):
		expected = str(expected)
	if isinstance(actual, (date, datetime, time)):
		actual = str(actual)
	return str(expected) == str(actual)


def _is_verified_attachment_url(
	doctype: str,
	name: str,
	fieldname: str,
	actual_url: Any,
	fieldtype: str | None,
) -> bool:
	"""Accept only a URL rewritten by the migrated target File lifecycle."""

	if fieldtype not in {"Attach", "Attach Image"} or not actual_url:
		return False
	return bool(
		frappe.db.exists(
			"File",
			{
				"is_folder": 0,
				"attached_to_doctype": doctype,
				"attached_to_name": name,
				"attached_to_field": fieldname,
				"file_url": str(actual_url),
			},
		)
	)


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
		expected_counts[doctype] = expected_counts.get(doctype, 0) + 1
	schema = plan.target_schemas[doctype]
	# Single DocTypes have no physical `tab<DocType>` table. Their one logical
	# identity is counted below, while field values live in tabSingles.
	if name and not schema.get("issingle"):
		pending.setdefault(doctype, []).append(str(name))
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
	audited_orphan_attachments = 0
	for row in source.iter_files(metadata_only=True):
		_validate_file_metadata(row, plan)
		if row.get("orphan_attachment"):
			if frappe.db.exists("File", row["name"]):
				failures.append(f"Unexpected migrated orphan File {row['name']}")
			else:
				audited_orphan_attachments += 1
			verified += 1
			continue
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
		"audited_orphan_attachment_count": audited_orphan_attachments,
		"source_file_bytes": int(status.get("file_bytes") or 0),
		"status": (
			"Pass With Audited Omissions"
			if not failures
			and verified == int(status.get("file_count") or 0)
			and (audited_missing_blobs or audited_orphan_attachments)
			else "Pass"
			if not failures and verified == int(status.get("file_count") or 0)
			else "Failed"
		),
		"failures": failures,
	}


def _verify_stock_summary(source: F15SourceBridge) -> dict[str, Any]:
	dimensions = _target_stock_dimension_fieldnames()
	source_summary = source.stock_summary_for_dimensions(dimensions)
	if list(source_summary.get("dimensions") or []) != dimensions:
		raise MigrationError("Source stock summary used a different dimension contract")
	target_summary = _target_stock_summary(dimensions)
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
		"target": target_summary,
	}


def _target_stock_summary(dimensions: Iterable[str]) -> dict[str, Any]:
	dimensions = [str(fieldname) for fieldname in dimensions]
	if any(not SAFE_SQL_FIELDNAME.fullmatch(fieldname) for fieldname in dimensions):
		raise MigrationError("Unsafe target stock dimension fieldname")
	columns = set(frappe.db.get_table_columns("Stock Ledger Entry"))
	missing = [fieldname for fieldname in dimensions if fieldname not in columns]
	if missing:
		raise MigrationError(
			"Target Stock Ledger Entry is missing configured dimensions: "
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
		""",
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
	return {
		"dimensions": dimensions,
		"bucket_count": len(rows),
		"bucket_digest": digest.hexdigest(),
		"total_qty": format(total_qty, "f"),
		"total_stock_value_difference": format(total_value, "f"),
	}


def _verify_link_integrity(
	plan: MigrationPlan,
	source_broken_links: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
	"""Check every static and dynamic Link in the migrated target schemas."""

	approved_by_field: dict[tuple[str, str, str], dict[str, str]] = {}
	for row in source_broken_links:
		key = (
			str(row.get("target_doctype") or ""),
			str(row.get("target_field") or ""),
			str(row.get("target_link_doctype") or ""),
		)
		approved_by_field.setdefault(key, {})[
			str(row.get("target_name") or "")
		] = str(row.get("value") or "")
	failures: list[str] = []
	checked_fields = 0
	broken_values = 0
	audited_broken_values = 0
	audited_exceptions: list[str] = []
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
					approved=approved_by_field.get(
						(doctype, fieldname, str(field["options"])), {}
					),
				)
				if broken:
					broken_values += broken["total"]
					audited_broken_values += broken["audited"]
					if broken["audited"]:
						audited_exceptions.append(
							f"{doctype}.{fieldname}: {broken['audited']} exact source-invalid values"
						)
					if broken["unexpected"]:
						failures.append(
							f"Broken Link {doctype}.{fieldname} -> {field['options']}: "
							f"{broken['unexpected']} unexpected values; samples={broken['samples']}"
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
		"status": (
			"Pass With Audited Source Exceptions"
			if not failures and audited_broken_values
			else "Pass"
			if not failures
			else "Failed"
		),
		"checked_link_fields": checked_fields,
		"broken_link_values": broken_values,
		"audited_broken_link_values": audited_broken_values,
		"unexpected_broken_link_values": broken_values - audited_broken_values,
		"audited_exceptions": audited_exceptions,
		"failures": failures,
	}


def _broken_static_link_count(
	doctype: str,
	fieldname: str,
	link_doctype: str,
	*,
	is_single: bool,
	approved: Mapping[str, str] | None = None,
) -> dict[str, Any] | None:
	if not frappe.db.exists("DocType", link_doctype):
		return {
			"total": 1,
			"audited": 0,
			"unexpected": 1,
			"samples": [f"missing target DocType {link_doctype}"],
		}
	if is_single:
		value = frappe.db.get_single_value(doctype, fieldname)
		if value and not frappe.db.exists(link_doctype, value):
			return {"total": 1, "audited": 0, "unexpected": 1, "samples": [str(value)]}
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
	approved = dict(approved or {})
	audited_rows: dict[str, str] = {}
	if approved:
		names = sorted(approved)
		for chunk in _chunks(names, 100):
			placeholders = ", ".join(["%s"] * len(chunk))
			rows = frappe.db.sql(
				f"SELECT source.name, source.{field} FROM {table} source "
				f"LEFT JOIN {link_table} linked ON linked.name=source.{field} "
				f"WHERE source.name IN ({placeholders}) AND linked.name IS NULL",
				chunk,
			)
			for name, value in rows:
				if str(approved.get(str(name))) == str(value):
					audited_rows[str(name)] = str(value)
	samples = frappe.db.sql(
		f"SELECT source.name, source.{field} FROM {table} source "
		f"LEFT JOIN {link_table} linked ON linked.name=source.{field} "
		f"WHERE COALESCE(source.{field}, '')<>'' AND linked.name IS NULL "
		f"LIMIT {10 + len(audited_rows)}"
	)
	unexpected_samples = [
		f"{name}={value}"
		for name, value in samples
		if audited_rows.get(str(name)) != str(value)
	][:10]
	return {
		"total": count,
		"audited": len(audited_rows),
		"unexpected": count - len(audited_rows),
		"samples": unexpected_samples,
	}


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


def _mark_reset_started(migration_name: str, before: Mapping[str, Any]) -> None:
	started_on = now_datetime()
	reset_started_on = before.get("reset_started_on") or started_on
	frappe.db.set_value(
		"MRP Data Migration",
		migration_name,
		{
			"status": "Running",
			"last_action": "Reset Target",
			"last_started_on": started_on,
			"last_completed_on": None,
			"processed_records": 0,
			"skipped_records": 0,
			"failed_records": 0,
			"error_log": None,
			"checkpoint_json": json.dumps(
				{
					"mode": "reset",
					"reset_started_on": str(reset_started_on),
					"preserved_series_values": before["preserved_series_values"],
					"reset_generated_deleted_document_names": list(
						before.get("reset_generated_deleted_document_names") or []
					),
					"reset_generated_comment_names": list(
						before.get("reset_generated_comment_names") or []
					),
				},
				sort_keys=True,
			),
		},
		update_modified=False,
	)
	# This field is labelled source records for the migration actions. During the
	# reset boundary it intentionally shows the exact reviewed deletion total.
	frappe.db.set_value(
		"MRP Data Migration",
		migration_name,
		"total_source_records",
		int(before["total"]),
		update_modified=False,
	)
	frappe.db.commit()


def _mark_reset_complete(migration_name: str, result: Mapping[str, Any]) -> None:
	frappe.db.set_value(
		"MRP Data Migration",
		migration_name,
		{
			"status": "Reset Complete",
			"last_completed_on": now_datetime(),
			"processed_records": result.get("processed") or 0,
			"skipped_records": 0,
			"failed_records": 0,
			"checkpoint_json": None,
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
