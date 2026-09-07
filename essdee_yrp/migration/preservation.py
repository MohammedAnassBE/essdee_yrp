"""Lossless auxiliary phases of the original load, not post-migration repairs.

Orphan child rows retain their original missing-parent references. Credentials
are re-encrypted when the source key works; otherwise their exact ciphertext is
preserved with an explicit source-key warning, never described as operational.
"""

from collections import Counter, defaultdict
from hmac import compare_digest
import json

import frappe
from frappe.utils.password import get_decrypted_password, set_encrypted_password

from essdee_yrp.migration.engine import (
	MigrationError,
	_contextual_child_spec,
	transform_document,
)


def transform_orphan(row, plan):
	parent_spec = plan.specs.get(row.get("parenttype"))
	if not parent_spec:
		raise MigrationError(f"Unmapped orphan parent DocType {row.get('parenttype')}")
	fieldname = row.get("parentfield")
	if fieldname in parent_spec.ignored_fields:
		raise MigrationError(f"Populated orphan context is ignored: {parent_spec.source}.{fieldname}")
	target_child = parent_spec.table_option_map.get(fieldname)
	return transform_document(
		row, plan,
		_spec_override=_contextual_child_spec(row, plan, target_child) if target_child else None,
	)


def auth_identity(row, plan):
	"""Resolve identities without ever including credential material in errors."""
	source_doctype, source_field = row.get("doctype"), row.get("fieldname")
	spec = plan.specs.get(source_doctype)
	if not spec or source_field in spec.ignored_fields:
		raise MigrationError(f"Unmapped credential field {source_doctype}.{source_field}")
	fieldname = spec.field_map.get(source_field, source_field)
	field = next((f for f in spec.target_schema.get("fields", [])
		if f.get("fieldname") == fieldname), None)
	if not field or field.get("fieldtype") != "Password":
		raise MigrationError(f"Missing target Password field {spec.target}.{fieldname}")
	name = spec.target if spec.target_schema.get("issingle") else row.get("name")
	if not name:
		raise MigrationError(f"Missing credential record identity for {source_doctype}")
	return spec.target, name, fieldname


def run_auth(plan, source, *, dry_run=False, verify=False):
	counts = Counter()
	unavailable = []
	orphans = []
	failures = []
	for row in source.iter_auth_rows():
		doctype, name, fieldname = auth_identity(row, plan)
		identity = {"doctype": doctype, "name": name, "fieldname": fieldname}
		is_single = bool(plan.specs[row["doctype"]].source_schema.get("issingle"))
		if not is_single and not isinstance(row.get("source_record_exists"), bool):
			raise MigrationError(f"Credential source-record evidence missing: {doctype} {name}")
		source_orphan = not is_single and not row["source_record_exists"]
		if source_orphan:
			orphans.append(identity)
		decryptable = bool(row.get("encrypted") and row.get("decryptable"))
		counts["total"] += 1
		counts["reencrypted" if decryptable else "raw_preserved"] += 1
		if row.get("encrypted") and not decryptable:
			unavailable.append(identity)
		if dry_run:
			continue
		if not is_single:
			target_exists = bool(frappe.db.exists(doctype, name))
			if source_orphan and target_exists:
				raise MigrationError(f"Orphan source credential collides with target record: {doctype} {name}")
			if not source_orphan and not target_exists:
				raise MigrationError(f"Credential target record missing: {doctype} {name}")
		# __Auth can legitimately outlive a deleted child. Preserve its value and
		# original identity without inventing a live record or dropping history.
		if verify:
			if decryptable:
				try:
					actual = get_decrypted_password(doctype, name, fieldname, raise_exception=False)
				except Exception:
					actual = None
				matches = actual is not None and compare_digest(
					str(actual).encode(), str(row["plaintext"]).encode()
				)
			else:
				actual = frappe.db.sql(
					"SELECT password, encrypted FROM __Auth WHERE doctype=%s AND name=%s AND fieldname=%s",
					(doctype, name, fieldname),
				)
				matches = bool(actual) and int(actual[0][1]) == int(row["encrypted"]) and compare_digest(
					str(actual[0][0]).encode(), str(row["password"]).encode()
				)
			if not matches:
				failures.append(f"Credential value mismatch: {doctype} {name}.{fieldname}")
		elif decryptable:
			set_encrypted_password(doctype, name, row["plaintext"], fieldname=fieldname)
		else:
			frappe.db.sql(
				"INSERT INTO __Auth (doctype,name,fieldname,password,encrypted) VALUES (%s,%s,%s,%s,%s) "
				"ON DUPLICATE KEY UPDATE password=VALUES(password),encrypted=VALUES(encrypted)",
				(doctype, name, fieldname, row["password"], int(row["encrypted"])),
			)
	return {
		**counts, "source_key_unavailable": unavailable, "source_orphans": orphans,
		"source_orphan_count": len(orphans), "failures": failures,
		"status": "Failed" if failures else "Preserved; source key unavailable" if unavailable else "Pass",
	}


def run_retired_archive(migration_name, source, *, dry_run=False, verify=False, allow_missing_files=False):
	"""Store retired-table history on the audit record, not in live successors."""
	records = []
	counts = Counter()
	missing_blobs = []
	for record in source.iter_retired_rows():
		records.append(record)
		counts[record["source_doctype"]] += 1
		if record.get("blob_issue"):
			missing_blobs.append({"name": record["row"]["name"], "issue": record["blob_issue"]})
		if len(records) > 10000:
			raise MigrationError("Retired source archive exceeds 10,000 rows; review a bounded archive design before loading")
	encoded = json.dumps(records, sort_keys=True, separators=(",", ":"), default=str)
	if missing_blobs and not (verify or allow_missing_files):
		raise MigrationError(f"{len(missing_blobs)} retired attachment blobs are unavailable in the source")
	failures = []
	if verify:
		stored = frappe.db.get_value('SD YRP MRP Data Migration', migration_name, "retired_source_rows_json")
		try:
			actual = json.loads(stored or "null") if isinstance(stored, str) else stored
		except (ValueError, TypeError):
			actual = None
		if actual != records:
			failures.append("Retired source-table archive differs from the frozen source")
	elif not dry_run:
		frappe.db.set_value('SD YRP MRP Data Migration', migration_name,
			"retired_source_rows_json", encoded, update_modified=False)
	return {"rows": len(records), "tables": dict(counts), "failures": failures,
		"missing_blob_count": len(missing_blobs), "missing_blobs": missing_blobs,
		"status": "Failed" if failures else "Pass"}


def run_preservation(plan, source, *, migration_name, dry_run=False, allow_missing_files=False):
	from essdee_yrp.migration.live import FrappeBulkTarget

	target = FrappeBulkTarget()
	batches = defaultdict(list)
	counts = Counter()
	for row in source.iter_orphan_children():
		document = transform_orphan(row, plan)
		doctype = document["doctype"]
		counts[doctype] += 1
		if not dry_run:
			batches[doctype].append(document)
			if len(batches[doctype]) >= 500:
				target.upsert_batch(doctype, batches.pop(doctype))
				frappe.db.commit()
	for doctype, batch in batches.items():
		target.upsert_batch(doctype, batch)
	auth = run_auth(plan, source, dry_run=dry_run)
	retired = run_retired_archive(migration_name, source, dry_run=dry_run, allow_missing_files=allow_missing_files)
	if not dry_run:
		frappe.db.commit()
	return {"orphan_children": dict(counts), "orphan_child_count": sum(counts.values()), "auth": auth, "retired_tables": retired}


def verify_orphan_values(plan, source):
	from essdee_yrp.migration.live import _verify_transformed_value_batch

	caches = {"columns_cache": {}, "fieldtypes_cache": {}, "numeric_scales_cache": {}}
	batch = []
	counts = Counter()
	failures = []

	def flush():
		if not batch:
			return
		result = _verify_transformed_value_batch(batch, plan, **caches)
		counts.update({key: result[key] for key in ("documents", "values")})
		failures.extend(result["failures"][:max(0, 100 - len(failures))])
		batch.clear()

	for row in source.iter_orphan_children():
		batch.append(transform_orphan(row, plan))
		if len(batch) >= 500:
			flush()
	flush()
	return {**counts, "failures": failures, "status": "Failed" if failures else "Pass"}
