"""Independent comparison of every active-app File column and physical bytes.

No migration writer/transformer is imported. Original SQL identities and values
are compared directly; only the reviewed namespace/field route and a validated
physical file relocation may differ. Source gaps stay explicit.
"""

import hashlib
import json
from collections import defaultdict
from pathlib import Path


def query(connection, sql, params=()):
	with connection.cursor() as cursor:
		cursor.execute(sql, params)
		return list(cursor.fetchall())


def physical_path(site_path, file_url):
	url = str(file_url or '')
	for prefix, relative in (('/private/files/', 'private/files'), ('/files/', 'public/files')):
		if url.startswith(prefix):
			root = (Path(site_path) / relative).resolve()
			path = (root / url[len(prefix):]).resolve()
			if path.is_relative_to(root):
				return path
	return None


def digest_file(path):
	if path is None or not path.is_file():
		return None
	digest, size = hashlib.md5(), 0
	try:
		with path.open('rb') as stream:
			while chunk := stream.read(1024 * 1024):
				digest.update(chunk)
				size += len(chunk)
	except OSError:
		return None
	return digest.hexdigest(), size


def plain(value):
	return json.loads(json.dumps(value, default=str))


class SourceBlobEvidence:
	"""Determine source availability from physical bytes, not an archive label."""

	def __init__(self, connection, site_path):
		if site_path is None:
			raise ValueError('A source site path is required for independent archived-blob checks')
		self.site_path = site_path
		self.candidates = defaultdict(set)
		self.digests = {}
		for row in query(connection, 'SELECT file_url,content_hash,file_size FROM tabFile WHERE is_folder=0'):
			self.candidates[(row['content_hash'], int(row['file_size'] or 0))].add(row['file_url'])

	def available(self, row):
		wanted = (row['content_hash'], int(row['file_size'] or 0))
		for url in self.candidates[wanted] | {row.get('file_url')}:
			path = physical_path(self.site_path, url)
			if path not in self.digests:
				self.digests[path] = digest_file(path)
			if self.digests[path] == wanted:
				return True
		return False


def source_file_rows(connection, plan, *, query_fn=None, unresolved=None):
	"""Independently collect both declared File owners and forward app references."""
	read = query_fn or query
	files = read(connection, 'SELECT * FROM tabFile WHERE is_folder=0 ORDER BY name')
	by_id = {row['name']: row for row in files}
	by_url = defaultdict(list)
	for row in files:
		if row['file_url']:
			by_url[row['file_url']].append(row['name'])
	selected = {row['name'] for row in files if row['attached_to_doctype'] in plan.specs}
	references = defaultdict(list)
	for doctype, spec in sorted(plan.specs.items()):
		for field in spec.source_schema.get('fields') or []:
			kind, fieldname = field.get('fieldtype'), field.get('fieldname')
			if kind not in {'Attach', 'Attach Image'} and not (kind == 'Link' and field.get('options') == 'File'):
				continue
			if spec.source_schema.get('issingle'):
				rows = read(connection, 'SELECT %s AS name,value FROM tabSingles WHERE doctype=%s AND field=%s',
					(doctype, doctype, fieldname))
			else:
				column = '`' + fieldname.replace('`', '``') + '`'
				table = '`tab' + doctype.replace('`', '``') + '`'
				rows = read(connection, f'SELECT name,{column} AS value FROM {table} WHERE COALESCE({column},\'\')<>\'\' ORDER BY name')
			for row in rows:
				ids = [row['value']] if kind == 'Link' and row['value'] in by_id else by_url.get(row['value'], []) if kind != 'Link' else []
				if not ids and row['value'] and unresolved is not None:
					unresolved.append({'doctype': doctype, 'name': row['name'], 'fieldname': fieldname,
						'fieldtype': kind, 'value': row['value']})
				for name in ids:
					selected.add(name)
					references[name].append({'doctype': doctype, 'name': row['name'], 'fieldname': fieldname})
	return [by_id[name] for name in sorted(selected)], dict(references)


def audit_attachments(source_db, target_db, plan, source_site_path, target_site_path):
	unresolved = []
	rows, references = source_file_rows(source_db, plan, unresolved=unresolved)
	candidates = defaultdict(set)
	for row in query(source_db, 'SELECT file_url,content_hash,file_size FROM tabFile WHERE is_folder=0'):
		candidates[(row['content_hash'], int(row['file_size'] or 0))].add(row['file_url'])
	actual, folders = {}, set()
	for offset in range(0, len(rows), 500):
		for row in query(target_db, 'SELECT * FROM tabFile WHERE name IN %s',
			(tuple(row['name'] for row in rows[offset:offset + 500]),)):
			actual[row['name']] = row
	for row in query(target_db, 'SELECT name FROM tabFile WHERE is_folder=1'):
		folders.add(row['name'])
	failures, source_gaps = [], []
	mismatches = values = verified_blobs = relocated = 0
	fields = defaultdict(int)
	digests = {}

	def fail(message):
		nonlocal mismatches
		mismatches += 1
		if len(failures) < 100:
			failures.append(message)

	def digest(path):
		if path not in digests:
			digests[path] = digest_file(path)
		return digests[path]

	unresolved_details = []
	for reference in unresolved:
		path = physical_path(source_site_path, reference['value']) if reference['fieldtype'] != 'Link' else None
		available = bool(path and path.is_file())
		unresolved_details.append({key: value for key, value in reference.items() if key != 'value'} |
			{'local_url': path is not None, 'source_bytes_available': available})
		if available:
			fail(f"Source app blob has no File metadata/export route: {reference['doctype']} {reference['name']}.{reference['fieldname']}")

	for row in rows:
		name = row['name']
		spec = plan.specs.get(row['attached_to_doctype'])
		stored = actual.get(name)
		expected = dict(row)
		if spec:
			expected['attached_to_doctype'] = spec.target
			if spec.source_schema.get('issingle') and row['attached_to_name'] == row['attached_to_doctype']:
				expected['attached_to_name'] = spec.target
			field = row['attached_to_field']
			expected['attached_to_field'] = spec.field_map.get(field, field) if field else field
		wanted = (row['content_hash'], int(row['file_size'] or 0))
		source_available = any(digest(physical_path(source_site_path, url)) == wanted
			for url in candidates[wanted])
		if not source_available:
			source_gaps.append(name)
		if stored is None:
			fail(f'Missing original File row: {name}')
			continue
		path = physical_path(target_site_path, stored['file_url'])
		target_available = digest(path) == wanted
		if source_available and not target_available:
			fail(f'Available source attachment bytes are missing/corrupt on target: {name}')
		elif path is not None and path.is_file() and not target_available:
			fail(f'Target attachment bytes conflict with original source metadata: {name}')
		if target_available:
			verified_blobs += 1
		if stored.get('file_url') != row['file_url']:
			prefix = '/private/files/' if row['is_private'] else '/files/'
			if target_available and str(stored.get('file_url') or '').startswith(prefix):
				expected['file_url'] = stored['file_url']
				relocated += 1
			else:
				fail(f'Unverified original attachment URL change: {name}')
		if row['folder'] and row['folder'] not in folders:
			fail(f'Missing original attachment folder: {name}')
		for field, value in expected.items():
			values += 1
			fields[field] += 1
			if field not in stored or plain(value) != plain(stored[field]):
				fail(f'Original File column mismatch: {name}.{field}')
	return {'status': 'Failed' if mismatches else 'Pass With Source Gaps' if source_gaps or unresolved else 'Pass',
		'rows': len(rows), 'field_values': values,
		'forward_referenced_file_count': len(references),
		'unowned_referenced_file_count': sum(not row['attached_to_doctype'] for row in rows),
		'references_without_source_file_metadata': unresolved_details,
		'missing_metadata_reference_count': len(unresolved_details),
		'field_inventory': dict(fields), 'mismatch_count': mismatches, 'failures': failures,
		'verified_blob_count': verified_blobs, 'validated_url_relocations': relocated,
		'missing_source_blob_count': len(source_gaps), 'missing_source_blobs': source_gaps,
		'method': 'Independent original File SQL columns, native folder links and streaming physical byte digests'}
