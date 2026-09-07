import gzip
import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography.fernet import Fernet

from essdee_yrp.migration.engine import MigrationError
from essdee_yrp.migration import framework_history as history


class FrameworkHistoryTest(unittest.TestCase):
	def record(self, name='C-1', doctype='Comment', **values):
		return {'source_doctype': doctype, 'row': {'name': name, 'reference_doctype': 'Supplier', **values}}

	def test_raw_archive_keeps_all_original_values_and_row_order(self):
		record = self.record(content='Tamil தமிழ்\nSecond line', retired_field=0, nullable=None)
		encoded = history.canonical_record(record)
		self.assertEqual(json.loads(encoded), record)
		with patch.object(history, 'CHUNK_ROWS', 2):
			chunks = list(history.iter_chunks([record, self.record('C-2'), self.record('C-3')]))
		self.assertEqual([len(chunk) for chunk in chunks], [2, 1])
		self.assertEqual(chunks[0][0][1], encoded)

	def test_archive_boundaries_do_not_drop_the_overflow_record(self):
		records = [self.record(str(index)) for index in range(4)]
		with patch.object(history, 'CHUNK_BYTES', len(history.canonical_record(records[0])) + 1):
			chunks = list(history.iter_chunks(records))
		self.assertEqual([row for chunk in chunks for row, _ in chunk], records)
		with patch.object(history, 'MAX_RECORD_BYTES', 1):
			with self.assertRaises(MigrationError):
				list(history.iter_chunks(records))

	def test_private_archive_readback_checks_owner_key_and_digest(self):
		raw = history.canonical_record(self.record())
		cipher = Fernet(Fernet.generate_key())
		doc = SimpleNamespace(is_private=1, attached_to_doctype=history.MIGRATION_DOCTYPE,
			attached_to_name='RUN', get_content=lambda: cipher.encrypt(gzip.compress(raw)))
		entry = {'file_id': 'FILE', 'sha256': hashlib.sha256(raw).hexdigest()}
		with patch.object(history.frappe, 'get_doc', return_value=doc), patch.object(history, 'cipher', return_value=cipher):
			self.assertEqual(history.read_archive_chunk(entry, 'RUN'), raw)
			with self.assertRaisesRegex(MigrationError, 'ownership'):
				history.read_archive_chunk(entry, 'OTHER-RUN')
			with self.assertRaisesRegex(MigrationError, 'digest'):
				history.read_archive_chunk({**entry, 'sha256': 'wrong'}, 'RUN')
			doc.is_private = 0
			with self.assertRaisesRegex(MigrationError, 'ownership'):
				history.read_archive_chunk(entry, 'RUN')

	def test_shares_workflows_and_retired_history_never_become_active_rows(self):
		plan = SimpleNamespace(specs={'Supplier': SimpleNamespace(target='YRP Supplier', source_schema={})})
		for doctype in ['DocShare', 'Document Share Key', 'Workflow Action', 'Communication', 'Report']:
			self.assertIsNone(history.native_projection(self.record(doctype=doctype), plan))
		self.assertIsNone(history.native_projection(self.record(reference_doctype='WO Debit'), plan))
		with patch('essdee_yrp.migration.live._transform_supporting_document', return_value={'name': 'C-1'}) as transform:
			self.assertEqual(history.native_projection(self.record(), plan), {'name': 'C-1'})
			self.assertEqual(transform.call_args.args[2], {'Supplier': 'YRP Supplier'})

	def test_renamed_single_history_points_to_the_target_single_identity(self):
		plan = SimpleNamespace(specs={'Settings': SimpleNamespace(target='YRP Settings', source_schema={'issingle': 1})})
		source = self.record(reference_doctype='Settings', reference_name='Settings')
		with patch('essdee_yrp.migration.live._transform_supporting_document', return_value={'reference_doctype': 'YRP Settings'}):
			self.assertEqual(history.native_projection(source, plan)['reference_name'], 'YRP Settings')

	def test_dry_run_never_writes_archive_or_timeline(self):
		source = SimpleNamespace(iter_framework_rows=lambda: iter([self.record(doctype='DocShare')]))
		with patch.object(history, 'save_archive_chunk') as save, patch.object(history, 'write_timeline') as write:
			result = history.run_framework_history(SimpleNamespace(specs={}), source, 'RUN', dry_run=True)
		self.assertEqual(result['rows'], 1)
		save.assert_not_called()
		write.assert_not_called()

	def test_missing_supporting_blobs_need_explicit_source_gap_mode(self):
		record = {'source_doctype': 'File', 'row': {'name': 'F-1'}, 'blob_issue': 'Unavailable'}
		source = SimpleNamespace(iter_framework_rows=lambda: iter([record]))
		with self.assertRaisesRegex(MigrationError, 'blob is unavailable'):
			history.run_framework_history(SimpleNamespace(specs={}), source, 'RUN', dry_run=True)
		result = history.run_framework_history(SimpleNamespace(specs={}), source, 'RUN', dry_run=True, allow_missing_files=True)
		self.assertEqual(result['missing_blob_count'], 1)

	def test_native_verification_compares_missing_and_changed_values_without_exposing_content(self):
		documents = [{'doctype': 'Comment', 'name': 'C-1', 'content': 'private original text'},
			{'doctype': 'Comment', 'name': 'C-2', 'content': 'missing row'}]
		with patch.object(history.frappe, 'get_meta', return_value=SimpleNamespace(fields=[])), \
			patch.object(history.frappe.db, 'sql', return_value=[history.frappe._dict(name='C-1', content='changed')]):
			result = history.verify_native(documents)
		self.assertEqual(result['mismatch_count'], 3)
		self.assertNotIn('private original text', str(result))

	def test_archive_resume_reuses_verified_existing_file(self):
		raw = history.canonical_record(self.record())
		with patch.object(history.frappe, 'get_all', return_value=['FILE']), \
			patch.object(history, 'read_archive_chunk', return_value=raw) as read:
			entry = history.save_archive_chunk(raw, 1, 'RUN')
		self.assertEqual(entry['file_id'], 'FILE')
		read.assert_called_once()

	def test_timeline_writer_rejects_changed_native_identity(self):
		target = Mock()
		document = {'doctype': 'Comment', 'name': 'C-1', 'owner': 'original'}
		with patch.object(history.frappe, 'get_all', return_value=[history.frappe._dict(name='C-1', owner='other')]):
			with self.assertRaisesRegex(MigrationError, 'independently changed'):
				history.write_timeline([document], target)
		target.upsert_batch.assert_not_called()

	def test_custom_folders_are_native_but_roots_and_attachments_remain_archived(self):
		plan = SimpleNamespace(specs={})
		for name, folder in [('Home', 1), ('Home/Attachments', 1), ('F-1', 0)]:
			self.assertIsNone(history.native_projection(
				{'source_doctype': 'File', 'row': {'name': name, 'is_folder': folder}}, plan))
		row = {'name': 'Home/product', 'is_folder': 1, 'folder': 'Home'}
		with patch('essdee_yrp.migration.live._transform_supporting_document', return_value={'doctype': 'File', **row}):
			self.assertEqual(history.native_projection({'source_doctype': 'File', 'row': row}, plan),
				{'doctype': 'File', **row})

	def test_custom_folder_collision_cannot_overwrite_target(self):
		target = Mock()
		row = {'doctype': 'File', 'name': 'Home/product', 'owner': 'original'}
		with patch.object(history.frappe, 'get_all', return_value=[history.frappe._dict(name=row['name'], owner='other')]):
			with self.assertRaisesRegex(MigrationError, 'independently changed'):
				history.write_timeline([row], target)
		target.upsert_batch.assert_not_called()
