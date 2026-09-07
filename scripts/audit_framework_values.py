"""Independent SQL/physical-file audit of the supporting framework closure.

No source bridge, migration transformer, or archive writer is imported. The
expected scope is reconstructed from stored SQL metadata and direct/reverse
links. Every archived SQL column is compared with the original source row.
Only counts, field identities and mismatch identities leave this module.
"""

import base64
import gzip
import hashlib
import io
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

from cryptography.fernet import Fernet
from pymysql.cursors import SSDictCursor

from audit_attachment_values import SourceBlobEvidence, source_file_rows

RETIRED = ('WO Debit', 'Employee Department', 'Item Production Detail Cloth Accessories',
	'Custom User Dashboard', 'Custom User Dashboard User')
NATIVE = {'Address', 'Contact', 'Dynamic Link', 'Contact Email', 'Contact Phone', 'Comment', 'Version', 'File'}


def quote(value):
	return '`' + str(value).replace('`', '``') + '`'


def query(connection, sql, params=()):
	with connection.cursor() as cursor:
		cursor.execute(sql, params)
		return list(cursor.fetchall())


def schema_columns(connection, doctype):
	return {row['column_name']: row for row in query(connection,
		'SELECT column_name,data_type FROM information_schema.columns '
		'WHERE table_schema=DATABASE() AND table_name=%s', ('tab' + doctype,))}


def source_scope(connection, plan):
	"""Reconstruct scope from SQL metadata, independently of the source bridge."""
	definitions = defaultdict(dict)
	for row in query(connection, 'SELECT parent,fieldname,fieldtype,options FROM tabDocField'):
		definitions[row['parent']][row['fieldname']] = row
	for row in query(connection, 'SELECT dt AS parent,fieldname,fieldtype,options FROM `tabCustom Field`'):
		definitions[row['parent']][row['fieldname']] = row
	for row in query(connection, 'SELECT doc_type,field_name,property,value FROM `tabProperty Setter` '
		"WHERE property IN ('fieldtype','options') AND COALESCE(field_name,'')<>''"):
		field = definitions[row['doc_type']].get(row['field_name'])
		if field:
			field[row['property']] = row['value']
	business = {'Address': set(), 'Contact': set()}
	for row in query(connection, 'SELECT DISTINCT parenttype,parent FROM `tabDynamic Link` '
		"WHERE parenttype IN ('Address','Contact') AND link_doctype IN %s", (tuple(plan.specs),)):
		business[row['parenttype']].add(row['parent'])
	for doctype, spec in plan.specs.items():
		for field in spec.source_schema.get('fields') or []:
			if field.get('fieldtype') != 'Link' or field.get('options') not in business:
				continue
			if spec.source_schema.get('issingle'):
				rows = query(connection, 'SELECT value FROM tabSingles WHERE doctype=%s AND field=%s',
					(doctype, field['fieldname']))
			else:
				rows = query(connection, f'SELECT DISTINCT {quote(field["fieldname"])} AS value FROM {quote("tab" + doctype)}')
			business[field['options']].update(row['value'] for row in rows if row['value'])
	if business['Contact']:
		business['Address'].update(row['address'] for row in query(connection,
			"SELECT DISTINCT address FROM tabContact WHERE name IN %s AND COALESCE(address,'')<>''",
			(tuple(sorted(business['Contact'])),)))
	app_types = tuple(sorted(set(plan.specs) | set(RETIRED)))
	predicates = {}
	for doctype, fields in sorted(definitions.items()):
		if doctype in app_types or doctype == 'File':
			continue
		controls = {f['fieldname']: None for f in fields.values()
			if f['fieldtype'] == 'Link' and f['options'] == 'DocType'}
		controls.update({f['options']: f['fieldname'] for f in fields.values()
			if f['fieldtype'] == 'Dynamic Link' and f['options']})
		if not controls:
			continue
		if doctype == 'Version':
			controls['ref_doctype'] = 'docname'
		columns = schema_columns(connection, doctype)
		parts, params = [], []
		for controller, reference in controls.items():
			if controller not in columns:
				continue
			parts.append(f'{quote(controller)} IN %s')
			params.append(app_types)
			if reference in columns:
				for master, names in sorted(business.items()):
					if names:
						parts.append(f'({quote(controller)}=%s AND {quote(reference)} IN %s)')
						params.extend((master, tuple(sorted(names))))
		if parts:
			predicates[doctype] = ('(' + ' OR '.join(parts) + ')', tuple(params))
	for master, names in business.items():
		if names:
			predicates[master] = ('name IN %s', (tuple(sorted(names)),))
	# Independently include history linked through app-owned reports/imports.
	# The source's Prepared Report uses a Data field for this relationship.
	for child, link, parent in (
		('Prepared Report', 'report_name', 'Report'),
		('Auto Email Report', 'report', 'Report'),
		('Data Import Log', 'data_import', 'Data Import'),
		('Number Card Link', 'card', 'Number Card'),
	):
		columns = schema_columns(connection, child)
		if parent not in predicates or not columns:
			continue
		if link not in columns:
			raise ValueError(f'Missing framework history relationship: {child}.{link}')
		condition, params = predicates[parent]
		clause = f'{quote(link)} IN (SELECT name FROM {quote("tab" + parent)} WHERE {condition})'
		if child in predicates:
			old, values = predicates[child]
			predicates[child] = (f'({old} OR {clause})', (*values, *params))
		else:
			predicates[child] = (clause, params)
	for parent, (condition, params) in list(predicates.items()):
		for field in definitions[parent].values():
			if field['fieldtype'] not in {'Table', 'Table MultiSelect'} or field['options'] in app_types:
				continue
			child = field['options']
			child_condition = '(parenttype=%s AND parentfield=%s AND parent IN '
			child_condition += f'(SELECT name FROM {quote("tab" + parent)} WHERE {condition}))'
			child_params = (parent, field['fieldname'], *params)
			if child in predicates:
				previous, previous_params = predicates[child]
				predicates[child] = (f'({previous} OR {child_condition})', (*previous_params, *child_params))
			else:
				predicates[child] = (child_condition, child_params)
	parts, params = [], []
	for doctype, (condition, values) in sorted(predicates.items()):
		parts.append('(attached_to_doctype=%s AND attached_to_name IN '
			f'(SELECT name FROM {quote("tab" + doctype)} WHERE {condition}))')
		params.extend((doctype, *values))
	if parts:
		predicates['File'] = ('(' + ' OR '.join(parts) + ')', tuple(params))
	condition, values = predicates.get('File', ('0=1', ()))
	app_files, _references = source_file_rows(connection, plan, query_fn=query)
	waiting = {row['folder'] for row in query(connection,
		"SELECT DISTINCT folder FROM tabFile WHERE is_folder=0 AND COALESCE(folder,'')<>'' "
		f"AND (COALESCE(attached_to_doctype,'') IN %s OR name IN %s OR ({condition}))",
		(app_types, tuple(row['name'] for row in app_files) or ('',), *values))}
	folders = set()
	while waiting:
		rows = query(connection, 'SELECT name,folder,is_folder FROM tabFile WHERE name IN %s', (tuple(sorted(waiting)),))
		if {row['name'] for row in rows} != waiting or any(not row['is_folder'] for row in rows):
			raise ValueError('Invalid source File folder ancestry')
		folders.update(waiting)
		waiting = {row['folder'] for row in rows if row['folder']} - folders
	if folders:
		predicates['File'] = (f'({condition} OR (is_folder=1 AND name IN %s))', (*values, tuple(sorted(folders))))
	return predicates


def expected_identity_inventory(connection, plan):
	result = {}
	for doctype, (condition, params) in source_scope(connection, plan).items():
		digest, count = hashlib.sha256(), 0
		with connection.cursor(SSDictCursor) as cursor:
			cursor.execute(f'SELECT name FROM {quote("tab" + doctype)} WHERE {condition} ORDER BY name', params)
			for row in cursor:
				digest.update(str(row['name']).encode() + b'\0')
				count += 1
		result[doctype] = {'rows': count, 'identity_digest': digest.hexdigest()}
	return result


def read_chunk_bytes(target_db, site_path, entry, migration_name, encryption_key):
	if entry.get('parts'):
		if (entry.get('bytes', 0) > 256 * 1024 * 1024 or len(entry['parts']) > 64
			or any(part.get('parts') for part in entry['parts'])
			or sum(part.get('bytes', 0) for part in entry['parts']) != entry['bytes']):
			raise ValueError('Invalid multipart archive bounds')
		raw = b''.join(read_chunk_bytes(target_db, site_path, part, migration_name, encryption_key)
			for part in entry['parts'])
		if len(raw) > 256 * 1024 * 1024 or len(raw) != entry['bytes'] or hashlib.sha256(raw).hexdigest() != entry['sha256']:
			raise ValueError('Multipart archive content digest mismatch')
		return raw
	files = query(target_db, 'SELECT is_private,attached_to_doctype,attached_to_name,file_url '
		'FROM tabFile WHERE name=%s', (entry['file_id'],))
	if len(files) != 1:
		raise ValueError('Missing archive File metadata')
	file = files[0]
	if (not file['is_private'] or file['attached_to_doctype'] != 'SD YRP MRP Data Migration'
		or file['attached_to_name'] != migration_name or not file['file_url'].startswith('/private/files/')):
		raise ValueError('Unsafe archive File ownership/location')
	root = (site_path / 'private' / 'files').resolve()
	path = (root / file['file_url'].removeprefix('/private/files/')).resolve()
	if not path.is_relative_to(root):
		raise ValueError('Archive File path escapes the target site')
	packed = Fernet(encryption_key.encode()).decrypt(path.read_bytes())
	with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
		raw = stream.read(4 * 1024 * 1024 + 1)
	if len(raw) > 4 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != entry['sha256']:
		raise ValueError('Archive content digest mismatch')
	return raw


def read_chunk(target_db, site_path, entry, migration_name, encryption_key):
	raw = read_chunk_bytes(target_db, site_path, entry, migration_name, encryption_key)
	records = [json.loads(line) for line in raw.splitlines()]
	if len(records) != entry['rows'] or len(raw) != entry['bytes']:
		raise ValueError('Archive chunk row/byte count mismatch')
	return records


def _plain(value):
	return json.loads(json.dumps(value, default=str))


def equal_sql_value(original, stored):
	"""Preserve SQL numeric value exactly, without a rounding tolerance.

	F15's framework DB adapter returns SQL DECIMAL as float. An archive's JSON
	15.0 and SQL Decimal('15.000000000') are the same number, but converting
	a large/fine-grained Decimal to a rounded float must still fail. Only an
	actual SQL Decimal gets numeric handling; Data strings never get coerced.
	"""
	if isinstance(original, Decimal):
		if stored is None or isinstance(stored, bool):
			return False
		try:
			value = Decimal(str(stored))
		except (InvalidOperation, TypeError, ValueError):
			return False
		return original.is_finite() and value.is_finite() and original == value
	return _plain(original) == _plain(stored)


def compare_sql_row(original, archived):
	if original is None or set(original) != set(archived):
		return False, 0
	if not all(equal_sql_value(value, archived[field]) for field, value in original.items()):
		return False, 0
	representations = sum(isinstance(value, Decimal) and _plain(value) != archived[field]
		for field, value in original.items())
	return True, representations


def audit_framework(source_db, target_db, plan, migration_name, site_path, encryption_key, *, source_site_path=None):
	manifest_rows = query(target_db, 'SELECT framework_archive_json FROM `tabSD YRP MRP Data Migration` WHERE name=%s',
		(migration_name,))
	manifest = json.loads(manifest_rows[0]['framework_archive_json'] or '{}') if manifest_rows else {}
	if manifest.get('state') != 'complete' or manifest.get('version') != 1:
		return {'status': 'Failed', 'mismatch_count': 1, 'failures': ['Complete encrypted framework archive is missing']}
	inventory = expected_identity_inventory(source_db, plan)
	print('AUDIT_FRAMEWORK_START expected_rows=' + str(sum(row['rows'] for row in inventory.values())), flush=True)
	next_progress = 100_000
	counts, native_counts, fields = Counter(), Counter(), defaultdict(Counter)
	digests = defaultdict(hashlib.sha256)
	mismatches = 0
	numeric_representation_matches = 0
	failures, missing_blobs = [], []
	source_blobs = None
	available_source_blobs = checked_source_blobs = 0
	native_columns = {doctype: schema_columns(target_db, doctype) for doctype in NATIVE}

	def fail(identity):
		nonlocal mismatches
		mismatches += 1
		if len(failures) < 100:
			failures.append(identity)

	for entry in manifest.get('chunks') or []:
		try:
			records = read_chunk(target_db, site_path, entry, migration_name, encryption_key)
		except Exception:
			fail('Encrypted framework chunk is missing, corrupt, or unreadable')
			continue
		groups = defaultdict(list)
		for record in records:
			doctype, row = record['source_doctype'], record['row']
			groups[doctype].append(record)
			counts[doctype] += 1
			digests[doctype].update(str(row['name']).encode() + b'\0')
		for doctype, group in groups.items():
			names = tuple(record['row']['name'] for record in group)
			original = {row['name']: row for row in query(source_db,
				f'SELECT * FROM {quote("tab" + doctype)} WHERE name IN %s', (names,))}
			native = {row['name']: row for row in query(target_db,
				f'SELECT * FROM {quote("tab" + doctype)} WHERE name IN %s', (names,))} if doctype in NATIVE else {}
			for record in group:
				row = record['row']
				name = row['name']
				matches, representations = compare_sql_row(original.get(name), row)
				numeric_representation_matches += representations
				if not matches:
					fail(f'Original SQL/archive mismatch: {doctype} {name}')
				for field in row:
					fields[doctype][field] += 1
				if doctype == 'File':
					if row.get('is_folder'):
						pass
					else:
						if source_blobs is None:
							source_blobs = SourceBlobEvidence(source_db, source_site_path)
						available = source_blobs.available(row)
						checked_source_blobs += 1
						available_source_blobs += int(available)
						if not available:
							missing_blobs.append({'name': name, 'issue': 'Source bytes unavailable/corrupt in independent disk check'})
						if record.get('blob_issue'):
							if available:
								fail(f'Available source file incorrectly archived as missing: {name}')
						elif record.get('blob_base64') is not None:
							blob = base64.b64decode(record['blob_base64'], validate=True)
							if len(blob) != int(row['file_size'] or 0) or hashlib.md5(blob).hexdigest() != row['content_hash']:
								fail(f'Archived file bytes differ from source metadata: {name}')
						else:
							fail(f'Archived File has neither bytes nor an explicit source gap: {name}')
				active = doctype in NATIVE
				if doctype == 'File':
					active = bool(row.get('is_folder') and row['name'] not in {'Home', 'Home/Attachments'})
				controller = 'reference_doctype' if doctype == 'Comment' else 'ref_doctype' if doctype == 'Version' else None
				if controller and row.get(controller) not in set(plan.specs) | {'Address', 'Contact'}:
					active = False
				if doctype == 'Dynamic Link' and row.get('parenttype') not in {'Address', 'Contact'}:
					active = False
				if not active:
					continue
				native_counts[doctype] += 1
				stored = native.get(name)
				if stored is None:
					fail(f'Missing native framework row: {doctype} {name}')
					continue
				for field, value in row.items():
					value = original.get(name, {}).get(field, value)
					if field not in native_columns[doctype]:
						if value not in (None, '', 0, False):
							fail(f'Populated framework field only archived, not native: {doctype} {name}.{field}')
						continue
					if field in {controller, 'parenttype'} or (doctype == 'Dynamic Link' and field == 'link_doctype'):
						value = plan.specs[value].target if value in plan.specs else value
					if controller and field == ('reference_name' if doctype == 'Comment' else 'docname'):
						spec = plan.specs.get(row.get(controller))
						if spec and spec.source_schema.get('issingle') and value == row.get(controller):
							value = spec.target
					if not equal_sql_value(value, stored.get(field)):
						fail(f'Native framework value mismatch: {doctype} {name}.{field}')
		processed = sum(counts.values())
		if processed >= next_progress:
			print(f'AUDIT_FRAMEWORK_PROGRESS rows={processed} mismatches={mismatches}', flush=True)
			next_progress = (processed // 100_000 + 1) * 100_000
	for doctype in set(inventory) | set(counts):
		expected = inventory.get(doctype)
		if not expected or expected['rows'] != counts[doctype] or expected['identity_digest'] != digests[doctype].hexdigest():
			fail(f'Independent framework identity scope mismatch: {doctype}')
	if dict(counts) != manifest.get('counts') or dict(native_counts) != manifest.get('native_counts'):
		fail('Framework manifest counts do not match archived contents')
	return {'status': 'Failed' if mismatches else 'Pass', 'mismatch_count': mismatches, 'failures': failures,
		'rows': sum(counts.values()), 'tables': dict(counts), 'native_tables': dict(native_counts),
		'field_values': sum(sum(values.values()) for values in fields.values()),
		'field_inventory': {doctype: dict(values) for doctype, values in fields.items()},
		'missing_blob_count': len(missing_blobs), 'missing_blobs': missing_blobs,
		'independently_checked_source_blobs': checked_source_blobs,
		'available_source_blobs': available_source_blobs,
		'numeric_representation_matches': numeric_representation_matches,
		'numeric_comparison': 'Exact SQL Decimal comparison; JSON number/string representation may differ, but no rounding is accepted',
		'method': 'Independent SQL scope, identity digests, every original SQL column, native values, and decrypted physical archive files'}
