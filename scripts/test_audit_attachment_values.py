import hashlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import audit_attachment_values as audit


class IndependentAttachmentTest(unittest.TestCase):
	def test_archived_blob_availability_checks_all_matching_physical_candidates(self):
		wanted = hashlib.md5(b'photo').hexdigest()
		rows = [dict(file_url=url, content_hash=wanted, file_size=5)
			for url in ('/files/bad.png', '/files/good.png')]
		def digest(path):
			return (wanted, 5) if path and path.name == 'good.png' else ('wrong', 5)
		with patch.object(audit, 'query', return_value=rows), patch.object(audit, 'digest_file', side_effect=digest):
			evidence = audit.SourceBlobEvidence(None, '/source')
			self.assertTrue(evidence.available(rows[0]))
			self.assertFalse(evidence.available({**rows[0], 'content_hash': 'different'}))

	def test_archived_blob_check_requires_an_explicit_source_path(self):
		with self.assertRaisesRegex(ValueError, 'source site path'):
			audit.SourceBlobEvidence(None, None)

	def test_independent_scope_includes_forward_references_without_file_owner(self):
		rows = [{'name': 'UNOWNED', 'attached_to_doctype': None, 'file_url': '/files/photo.png'},
			{'name': 'UNRELATED', 'attached_to_doctype': None, 'file_url': '/files/other.png'}]
		def query(connection, sql, params=()):
			return rows if 'FROM tabFile' in sql else [{'name': 'PHOTO-1', 'value': '/files/photo.png'}]
		plan = SimpleNamespace(specs={'Product Image': SimpleNamespace(source_schema={
			'fields': [{'fieldname': 'image', 'fieldtype': 'Attach Image'}]})})
		selected, references = audit.source_file_rows(None, plan, query_fn=query)
		self.assertEqual([r['name'] for r in selected], ['UNOWNED'])
		self.assertEqual(references['UNOWNED'][0]['name'], 'PHOTO-1')

	def test_unindexed_source_image_is_reported_and_available_omitted_bytes_fail(self):
		def query(connection, sql, params=()):
			return [{'name': 'PHOTO-1', 'value': '/files/unindexed.png'}] if 'FROM `tabProduct Image`' in sql else []
		plan = SimpleNamespace(specs={'Product Image': SimpleNamespace(source_schema={
			'fields': [{'fieldname': 'image', 'fieldtype': 'Attach Image'}]})})
		for exists in (False, True):
			with patch.object(audit, 'query', side_effect=query), patch.object(Path, 'is_file', return_value=exists):
				result = audit.audit_attachments(None, None, plan, '/source', '/target')
			self.assertEqual(result['missing_metadata_reference_count'], 1)
			self.assertEqual(result['mismatch_count'], int(exists))
			self.assertEqual(result['status'], 'Failed' if exists else 'Pass With Source Gaps')

	def check(self, *, changed=None, source_available=True, target_available=True,
		missing=False, folders=('Home/product',), single=False, corrupt=False):
		source_db, target_db = object(), object()
		row = {'name': 'FILE-1', 'file_name': 'photo.png', 'file_type': 'PNG',
			'folder': 'Home/product', 'is_folder': 0, 'is_private': 1,
			'attached_to_doctype': 'Settings' if single else 'Item',
			'attached_to_name': 'Settings' if single else 'ITEM-1',
			'attached_to_field': 'photo', 'file_url': '/private/files/photo.png',
			'content_hash': hashlib.md5(b'photo').hexdigest(), 'file_size': 5,
			'nullable': None, 'zero_value': 0}
		stored = {**row, 'attached_to_doctype': 'YRP ' + row['attached_to_doctype'],
			'attached_to_field': 'image', **(changed or {})}
		if single:
			stored['attached_to_name'] = 'YRP Settings'
		def query(connection, sql, params=()):
			if connection is source_db:
				return [row]
			if 'is_folder=1' in sql:
				return [{'name': name} for name in folders]
			return [] if missing else [stored]
		def digest(path):
			available = source_available if str(path).startswith('/source/') else target_available
			return (row['content_hash'], 5) if available else ('wrong', 9) if corrupt else None
		plan = SimpleNamespace(specs={row['attached_to_doctype']: SimpleNamespace(
			target='YRP ' + row['attached_to_doctype'], field_map={'photo': 'image'},
			source_schema={'issingle': int(single)})})
		with patch.object(audit, 'query', side_effect=query), \
			patch.object(audit, 'digest_file', side_effect=digest), \
			patch.object(Path, 'is_file', return_value=corrupt):
			return audit.audit_attachments(source_db, target_db, plan, '/source', '/target')

	def test_every_column_and_single_identity_are_checked(self):
		for single in (False, True):
			result = self.check(single=single)
			self.assertEqual(result['mismatch_count'], 0)
			self.assertEqual(result['field_inventory']['file_type'], 1)
			self.assertEqual(result['verified_blob_count'], 1)

	def test_omitted_metadata_and_folder_are_failures(self):
		for field in ('file_type', 'folder', 'zero_value'):
			self.assertGreater(self.check(changed={field: None})['mismatch_count'], 0)
		self.assertGreater(self.check(folders=())['mismatch_count'], 0)

	def test_missing_source_bytes_never_excuse_missing_metadata(self):
		result = self.check(source_available=False, target_available=False)
		self.assertEqual(result['mismatch_count'], 0)
		self.assertEqual(result['status'], 'Pass With Source Gaps')
		self.assertEqual(result['missing_source_blob_count'], 1)
		self.assertGreater(self.check(source_available=False, missing=True)['mismatch_count'], 0)

	def test_missing_or_corrupt_target_bytes_fail(self):
		self.assertGreater(self.check(target_available=False)['mismatch_count'], 0)
		self.assertGreater(self.check(source_available=False, target_available=False, corrupt=True)['mismatch_count'], 0)

	def test_only_verified_same_privacy_url_relocation_is_allowed(self):
		result = self.check(changed={'file_url': '/private/files/moved.png'})
		self.assertEqual(result['mismatch_count'], 0)
		self.assertEqual(result['validated_url_relocations'], 1)
		self.assertGreater(self.check(changed={'file_url': '/files/public.png'})['mismatch_count'], 0)
		self.assertGreater(self.check(changed={'file_url': '/private/files/moved.png'},
			target_available=False)['mismatch_count'], 0)

	def test_path_traversal_and_external_urls_are_not_opened(self):
		for url in ('/files/../../site_config.json', '/private/files/../../site_config.json',
			'https://example.test/file.png'):
			self.assertIsNone(audit.physical_path('/site', url))
		self.assertEqual(audit.physical_path('/site', '/files/photo.png'), Path('/site/public/files/photo.png'))
