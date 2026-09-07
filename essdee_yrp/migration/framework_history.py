"""Original-load preservation of related framework data, with no side effects.

All source SQL values are kept in bounded, encrypted private archive chunks.
Comment/Version timeline rows and custom attachment folders are restored natively.
Installation-owned folder roots retain their target metadata. Workflow,
sharing, notification, import, report and integration configuration is inert.
Address/Contact and their children are verified here as well as loaded through
the supporting-master phase. No scheduler, mail, or permission hooks are run.
"""

import gzip
import hashlib
import io
import json
from collections import Counter, defaultdict

import frappe
from cryptography.fernet import Fernet

from essdee_yrp.migration.engine import MigrationError

MIGRATION_DOCTYPE = 'SD YRP MRP Data Migration'
MANIFEST_FIELD = 'framework_archive_json'
ARCHIVE_VERSION = 1
CHUNK_ROWS = 5000
CHUNK_BYTES = 4 * 1024 * 1024
MAX_RECORD_BYTES = 256 * 1024 * 1024
BUSINESS_TYPES = {'Address', 'Contact', 'Contact Email', 'Contact Phone', 'Dynamic Link'}
TIMELINE_TYPES = {'Comment', 'Version'}
NATIVE_WRITE_TYPES = TIMELINE_TYPES | {'File'}


def canonical_record(record):
	return (json.dumps(record, sort_keys=True, separators=(',', ':'), default=str) + '\n').encode()


def iter_chunks(records):
	buffer, size = [], 0
	for record in records:
		encoded = canonical_record(record)
		if len(encoded) > MAX_RECORD_BYTES:
			raise MigrationError(f'Source framework record {record["source_doctype"]} {record["row"]["name"]} '
				f'has {len(encoded)} bytes, exceeding the reviewed archive size limit')
		if buffer and (len(buffer) >= CHUNK_ROWS or size + len(encoded) > CHUNK_BYTES):
			yield buffer
			buffer, size = [], 0
		buffer.append((record, encoded))
		size += len(encoded)
	if buffer:
		yield buffer


def cipher():
	key = frappe.conf.get('encryption_key')
	if not key:
		raise MigrationError('The target encryption key is required for the private framework archive')
	return Fernet(key.encode() if isinstance(key, str) else key)


def read_archive_chunk(entry, migration_name):
	if entry.get('parts'):
		if (entry.get('bytes', 0) > MAX_RECORD_BYTES or len(entry['parts']) > 64
			or any(part.get('parts') for part in entry['parts'])
			or sum(part.get('bytes', 0) for part in entry['parts']) != entry['bytes']):
			raise MigrationError('Invalid multipart framework archive bounds')
		raw = b''.join(read_archive_chunk(part, migration_name) for part in entry['parts'])
		if len(raw) != entry['bytes'] or len(raw) > MAX_RECORD_BYTES or hashlib.sha256(raw).hexdigest() != entry['sha256']:
			raise MigrationError('Multipart framework archive content digest mismatch')
		return raw
	document = frappe.get_doc('File', entry['file_id'])
	if not (document.is_private and document.attached_to_doctype == MIGRATION_DOCTYPE
		and document.attached_to_name == migration_name):
		raise MigrationError('Framework archive File ownership/private flag mismatch')
	content = document.get_content()
	if isinstance(content, str):
		content = content.encode()
	try:
		packed = cipher().decrypt(content)
		with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
			raw = stream.read(CHUNK_BYTES + 1)
	except Exception as exc:
		raise MigrationError('Framework archive cannot be decrypted/read with the target key') from exc
	if len(raw) > CHUNK_BYTES or hashlib.sha256(raw).hexdigest() != entry['sha256']:
		raise MigrationError('Framework archive content digest mismatch')
	return raw


def save_archive_chunk(raw, rows, migration_name, previous=None):
	digest = hashlib.sha256(raw).hexdigest()
	if previous:
		if previous.get('sha256') != digest or previous.get('rows') != rows or read_archive_chunk(previous, migration_name) != raw:
			raise MigrationError('Previous framework archive checkpoint differs from the source')
		return previous
	if len(raw) > CHUNK_BYTES:
		parts = [save_archive_chunk(raw[offset:offset + CHUNK_BYTES], 0, migration_name)
			for offset in range(0, len(raw), CHUNK_BYTES)]
		return {'sha256': digest, 'rows': rows, 'bytes': len(raw), 'parts': parts}
	run_key = hashlib.sha256(migration_name.encode()).hexdigest()[:12]
	filename = f'mrp-history-{run_key}-{digest}.jsonl.gz.enc'
	filters = {'attached_to_doctype': MIGRATION_DOCTYPE, 'attached_to_name': migration_name,
		'file_name': filename}
	existing = frappe.get_all('File', filters=filters, pluck='name')
	if len(existing) > 1:
		raise MigrationError('Duplicate framework archive identity; review before resuming')
	if existing:
		entry = {'file_id': existing[0], 'sha256': digest, 'rows': rows, 'bytes': len(raw)}
		if read_archive_chunk(entry, migration_name) != raw:
			raise MigrationError('Existing framework archive differs from the source')
		return entry
	content = cipher().encrypt(gzip.compress(raw, mtime=0))
	# Let File own creation and rollback cleanup; do not pre-write the blob.
	document = frappe.get_doc({'doctype': 'File', 'file_name': filename, 'content': content,
		'is_private': 1, 'attached_to_doctype': MIGRATION_DOCTYPE,
		'attached_to_name': migration_name}).insert(ignore_permissions=True)
	entry = {'file_id': document.name, 'sha256': digest, 'rows': rows, 'bytes': len(raw)}
	if read_archive_chunk(entry, migration_name) != raw:
		raise MigrationError('New framework archive failed its immediate read-back check')
	return entry


def native_projection(record, plan):
	from essdee_yrp.migration.live import _transform_supporting_document

	doctype, row = record['source_doctype'], record['row']
	if doctype == 'File':
		# Preserve app-owned folder hierarchy without replacing installation-owned
		# root metadata. The archive still retains the original roots' values.
		if not row.get('is_folder') or row['name'] in {'Home', 'Home/Attachments'}:
			return None
	elif doctype not in BUSINESS_TYPES | TIMELINE_TYPES:
		return None
	if doctype == 'Dynamic Link' and row.get('parenttype') not in {'Address', 'Contact'}:
		return None
	if doctype in TIMELINE_TYPES:
		controller = 'reference_doctype' if doctype == 'Comment' else 'ref_doctype'
		if row.get(controller) not in set(plan.specs) | {'Address', 'Contact'}:
			return None  # Retired-parent history is preserved only in the archive.
	output = _transform_supporting_document(row, doctype,
		{name: spec.target for name, spec in plan.specs.items()})
	if doctype in TIMELINE_TYPES:
		spec = plan.specs.get(row.get(controller))
		name_field = 'reference_name' if doctype == 'Comment' else 'docname'
		if spec and spec.source_schema.get('issingle') and row.get(name_field) == row.get(controller):
			output[name_field] = spec.target
	return output


def _native_batches(documents):
	groups = defaultdict(list)
	for document in documents:
		groups[document['doctype']].append(document)
	for doctype, group in groups.items():
		for offset in range(0, len(group), 250):
			yield doctype, group[offset:offset + 250]


def checked_timeline_batches(documents):
	from essdee_yrp.migration.live import _same_migrated_value

	for doctype, batch in _native_batches(d for d in documents if d['doctype'] in NATIVE_WRITE_TYPES):
		existing = {row.name: row for row in frappe.get_all(doctype,
			filters={'name': ['in', [d['name'] for d in batch]]},
			fields=['name', 'owner', 'modified_by', 'creation', 'modified'])}
		for document in batch:
			actual = existing.get(document['name'])
			if actual and any(not _same_migrated_value(document.get(field), actual.get(field), 'Data')
				for field in ('owner', 'modified_by', 'creation', 'modified')):
				raise MigrationError(f'Refusing to overwrite independently changed {doctype} {document["name"]}')
		yield doctype, batch


def write_timeline(documents, target):
	for doctype, batch in checked_timeline_batches(documents):
		target.upsert_batch(doctype, batch)


def verify_native(documents):
	from essdee_yrp.migration.live import _quote_identifier, _same_migrated_value

	result = {'rows': 0, 'values': 0, 'mismatch_count': 0, 'failures': []}
	for doctype, batch in _native_batches(documents):
		fields = {f.fieldname: f.fieldtype for f in frappe.get_meta(doctype).fields}
		actual = {row.name: row for row in frappe.db.sql(
			f'SELECT * FROM {_quote_identifier("tab" + doctype)} WHERE name IN %s',
			(tuple(d['name'] for d in batch),), as_dict=True)}
		for document in batch:
			result['rows'] += 1
			stored = actual.get(document['name'])
			for field, value in document.items():
				if field == 'doctype':
					continue
				result['values'] += 1
				if stored is None or field not in stored or not _same_migrated_value(value, stored[field], fields.get(field)):
					result['mismatch_count'] += 1
					if len(result['failures']) < 100:
						result['failures'].append(f'Framework value mismatch: {doctype} {document["name"]}.{field}')
	return result


def run_framework_history(plan, source, migration_name, *, dry_run=False, verify=False, allow_missing_files=False):
	from essdee_yrp.migration.live import FrappeBulkTarget

	manifest = {'version': ARCHIVE_VERSION, 'state': 'partial', 'chunks': []}
	stored = json.loads(frappe.db.get_value(MIGRATION_DOCTYPE, migration_name, MANIFEST_FIELD) or '{}') if not dry_run else {}
	if verify and (stored.get('version') != ARCHIVE_VERSION or stored.get('state') != 'complete'):
		raise MigrationError('A complete framework archive from the original migration is required')
	previous_chunks = {entry['sha256']: entry for entry in stored.get('chunks') or []}
	counts, native_counts = Counter(), Counter()
	failures, missing_files = [], []
	value_count = mismatch_count = 0
	target = FrappeBulkTarget()
	for index, chunk in enumerate(iter_chunks(source.iter_framework_rows())):
		native = []
		for record, _encoded in chunk:
			counts[record['source_doctype']] += 1
			if record.get('blob_issue'):
				missing_files.append({'name': record['row']['name'], 'issue': record['blob_issue']})
				if not (allow_missing_files or verify):
					raise MigrationError('A supporting/history source attachment blob is unavailable')
			document = native_projection(record, plan)
			if document is not None:
				native.append(document)
				native_counts[document['doctype']] += 1
		raw = b''.join(encoded for _record, encoded in chunk)
		if verify:
			entries = stored.get('chunks') or []
			if index >= len(entries) or read_archive_chunk(entries[index], migration_name) != raw:
				mismatch_count += 1
				failures.append(f'Framework source/archive mismatch at chunk {index + 1}')
			result = verify_native(native)
			value_count += result['values']
			mismatch_count += result['mismatch_count']
			failures.extend(result['failures'][:max(0, 100 - len(failures))])
		elif dry_run:
			for _doctype, _batch in checked_timeline_batches(native):
				pass
		elif not dry_run:
			write_timeline(native, target)
			entry = save_archive_chunk(raw, len(chunk), migration_name,
				previous=previous_chunks.get(hashlib.sha256(raw).hexdigest()))
			manifest['chunks'].append(entry)
			frappe.db.set_value(MIGRATION_DOCTYPE, migration_name, MANIFEST_FIELD,
				json.dumps(manifest, sort_keys=True), update_modified=False)
			frappe.db.commit()
	manifest.update(state='complete', counts=dict(counts), native_counts=dict(native_counts))
	if verify:
		if stored.get('counts') != dict(counts) or stored.get('native_counts') != dict(native_counts):
			mismatch_count += 1
			failures.append('Framework archive scope counts differ from the source')
		if len(stored.get('chunks') or []) != (index + 1 if counts else 0):
			mismatch_count += 1
			failures.append('Framework archive has missing or extra chunks')
	elif not dry_run:
		frappe.db.set_value(MIGRATION_DOCTYPE, migration_name, MANIFEST_FIELD,
			json.dumps(manifest, sort_keys=True), update_modified=False)
		frappe.db.commit()
	return {'rows': sum(counts.values()), 'tables': dict(counts), 'native_tables': dict(native_counts),
		'verified_native_values': value_count, 'mismatch_count': mismatch_count, 'failures': failures,
		'missing_blob_count': len(missing_files), 'missing_blobs': missing_files,
		'archive_encrypted': True, 'status': 'Failed' if failures else 'Pass'}
