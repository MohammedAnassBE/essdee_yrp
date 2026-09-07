import hashlib
import json
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import audit_framework_values as audit


class IndependentFrameworkAuditTest(unittest.TestCase):
	def test_sql_decimal_representation_is_exact_not_textual(self):
		for stored in (15.0, 15, '15.0', Decimal('15.000')):
			with self.subTest(stored=stored):
				self.assertTrue(audit.equal_sql_value(Decimal('15.000000000'), stored))
		self.assertEqual(audit.compare_sql_row(
			{'name': 'PF', 'margin': Decimal('15.000000000')},
			{'name': 'PF', 'margin': 15.0}), (True, 1))

	def test_decimal_precision_loss_is_never_waived(self):
		for original in ('9007199254740993', '0.123456789123456789', '15.000000001'):
			stored = 15.0 if original.startswith('15.') else float(original)
			with self.subTest(original=original):
				self.assertFalse(audit.equal_sql_value(Decimal(original), stored))
		for stored in (None, True, False, float('nan'), float('inf'), 'invalid'):
			with self.subTest(stored=stored):
				self.assertFalse(audit.equal_sql_value(Decimal('0'), stored))

	def test_data_strings_and_missing_columns_are_not_numeric_matches(self):
		self.assertFalse(audit.equal_sql_value('15', 15))
		self.assertFalse(audit.equal_sql_value('15.0', '15.000'))
		self.assertEqual(audit.compare_sql_row(None, {'name': 'PF'}), (False, 0))
		self.assertEqual(audit.compare_sql_row({'name': 'PF'}, {'name': 'PF', 'x': None}), (False, 0))
		self.assertEqual(audit.compare_sql_row({'name': 'PF', 'x': None}, {'name': 'PF'}), (False, 0))

	def test_missing_blob_label_is_checked_against_source_disk(self):
		row = dict(name='FILE-1', file_size=5, content_hash=hashlib.md5(b'photo').hexdigest(),
			file_url='/private/files/photo.png', is_folder=0)
		record = {'source_doctype': 'File', 'row': row, 'blob_issue': 'Source blob unavailable'}
		manifest = {'version': 1, 'state': 'complete', 'chunks': [{}], 'counts': {'File': 1}, 'native_counts': {}}
		inventory = {'File': {'rows': 1, 'identity_digest': hashlib.sha256(b'FILE-1\0').hexdigest()}}
		def query(connection, sql, params=()):
			return [{'framework_archive_json': json.dumps(manifest)}] if 'framework_archive_json' in sql else [row]
		for available in (False, True):
			with self.subTest(available=available), \
				patch.object(audit, 'query', side_effect=query), \
				patch.object(audit, 'expected_identity_inventory', return_value=inventory), \
				patch.object(audit, 'read_chunk', return_value=[record]), \
				patch.object(audit, 'schema_columns', return_value={}), \
				patch.object(audit, 'SourceBlobEvidence') as evidence:
				evidence.return_value.available.return_value = available
				result = audit.audit_framework(None, None, SimpleNamespace(specs={}), 'RUN', Path('/target'),
					'key', source_site_path=Path('/source'))
				self.assertEqual(result['mismatch_count'], int(available))
				self.assertEqual(result['missing_blob_count'], int(not available))
				self.assertEqual(result['independently_checked_source_blobs'], 1)

	def test_independent_folder_scope_includes_ancestors_and_refuses_missing_parent(self):
		folders = {'Home/product': 'Home', 'Home': None}
		def query(connection, sql, params=()):
			if 'SELECT DISTINCT folder FROM tabFile' in sql:
				return [{'folder': 'Home/product'}]
			if 'SELECT name,folder,is_folder FROM tabFile' in sql:
				return [{'name': name, 'folder': folders[name], 'is_folder': 1}
					for name in params[0] if name in folders]
			return []
		plan = SimpleNamespace(specs={})
		with patch.object(audit, 'query', side_effect=query), patch.object(audit, 'schema_columns', return_value={}):
			scope = audit.source_scope(None, plan)
			self.assertEqual(scope['File'][1][-1], ('Home', 'Home/product'))
			del folders['Home']
			with self.assertRaisesRegex(ValueError, 'folder'):
				audit.source_scope(None, plan)

	def test_scope_includes_indirect_import_and_report_history(self):
		definitions = [dict(parent=dt, fieldname=field, fieldtype='Link', options='DocType')
			for dt, field in [('Report', 'ref_doctype'), ('Data Import', 'reference_doctype'), ('Number Card', 'document_type')]]
		def query(connection, sql, params=()):
			return definitions if 'FROM tabDocField' in sql else []
		columns = {'Prepared Report': {'name': {}, 'report_name': {}},
			'Auto Email Report': {'name': {}, 'report': {}},
			'Data Import Log': {'name': {}, 'data_import': {}},
			'Number Card Link': {'name': {}, 'card': {}}}
		columns.update({row['parent']: {'name': {}, row['fieldname']: {}} for row in definitions})
		plan = SimpleNamespace(specs={'Supplier': SimpleNamespace(source_schema={'fields': []})})
		with patch.object(audit, 'query', side_effect=query), \
			patch.object(audit, 'schema_columns', side_effect=lambda conn, dt: columns.get(dt, {})):
			scope = audit.source_scope(None, plan)
		for doctype in ('Prepared Report', 'Auto Email Report', 'Data Import Log', 'Number Card Link'):
			self.assertIn(doctype, scope)
			self.assertIn('IN (SELECT name FROM', scope[doctype][0])
			self.assertIn(doctype, scope['File'][1])
		self.assertIn('`report_name`', scope['Prepared Report'][0])

	def check(self, *, target_value='YRP Supplier', archive_value='original', inventory_rows=1):
		source_db, target_db = object(), object()
		source_row = {'name': 'C-1', 'content': 'original', 'reference_doctype': 'Supplier'}
		record = {'source_doctype': 'Comment', 'row': {**source_row, 'content': archive_value}}
		manifest = {'version': 1, 'state': 'complete', 'chunks': [{}],
			'counts': {'Comment': 1}, 'native_counts': {'Comment': 1}}
		inventory = {'Comment': {'rows': inventory_rows,
			'identity_digest': hashlib.sha256(b'C-1\0').hexdigest()}}
		def query(connection, sql, params=()):
			if 'framework_archive_json' in sql:
				return [{'framework_archive_json': json.dumps(manifest)}]
			return [source_row if connection is source_db else {**source_row, 'reference_doctype': target_value}]
		plan = SimpleNamespace(specs={'Supplier': SimpleNamespace(target='YRP Supplier', source_schema={})})
		with patch.object(audit, 'query', side_effect=query), \
			patch.object(audit, 'expected_identity_inventory', return_value=inventory), \
			patch.object(audit, 'read_chunk', return_value=[record]), \
			patch.object(audit, 'schema_columns', return_value={name: {} for name in source_row}):
			return audit.audit_framework(source_db, target_db, plan, 'RUN', Path('/unused'), 'unused')

	def test_exact_original_and_native_namespace_pass(self):
		result = self.check()
		self.assertEqual(result['mismatch_count'], 0)
		self.assertEqual(result['field_values'], 3)

	def test_wrong_native_namespace_fails(self):
		self.assertGreater(self.check(target_value='Supplier')['mismatch_count'], 0)

	def test_changed_archive_value_fails(self):
		result = self.check(archive_value='changed private text')
		self.assertGreater(result['mismatch_count'], 0)
		self.assertNotIn('changed private text', str(result))

	def test_scope_omissions_fail_even_when_every_archived_row_matches(self):
		self.assertGreater(self.check(inventory_rows=2)['mismatch_count'], 0)

	def test_missing_manifest_cannot_be_reported_as_pass(self):
		with patch.object(audit, 'query', return_value=[]):
			result = audit.audit_framework(None, None, None, 'RUN', Path('/unused'), None)
		self.assertEqual(result['status'], 'Failed')

	def test_oversized_multipart_manifest_is_rejected_before_file_reads(self):
		entry = {'bytes': 257 * 1024 * 1024, 'parts': [{'bytes': 1}]}
		with self.assertRaisesRegex(ValueError, 'bounds'):
			audit.read_chunk_bytes(None, Path('/unused'), entry, 'RUN', 'unused')
