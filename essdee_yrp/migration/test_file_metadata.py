import unittest
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from essdee_yrp.migration import live
from essdee_yrp.migration.engine import MigrationError


class CompleteFileMetadataTest(unittest.TestCase):
	def setUp(self):
		self.raw = {'name': 'FILE-1', 'file_type': 'PNG', 'folder': 'Home/product',
			'file_size': 0, 'file_url': '/files/image.png', 'is_private': 0,
			'attached_to_doctype': 'Settings', 'attached_to_name': 'Settings',
			'attached_to_field': 'photo', 'nullable': None, 'is_folder': 0}
		self.row = {**self.raw, 'source_file_metadata': dict(self.raw)}
		self.plan = SimpleNamespace(specs={'Settings': SimpleNamespace(target='YRP Settings',
			field_map={'photo': 'image'}, source_schema={'issingle': 1})})

	def test_all_source_values_survive_with_only_explicit_routes(self):
		with patch.object(live.frappe.db, 'get_table_columns', return_value=list(self.raw)):
			values = live._file_metadata_values(self.row, self.plan)
			moved = live._file_metadata_values(self.row, self.plan, file_url='/files/moved.png')
		self.assertEqual(values, {**self.raw, 'attached_to_doctype': 'YRP Settings',
			'attached_to_name': 'YRP Settings', 'attached_to_field': 'image'})
		self.assertEqual(moved, {**values, 'file_url': '/files/moved.png'})
		self.assertEqual(self.row['source_file_metadata'], self.raw)

	def test_missing_original_metadata_or_identity_fails(self):
		for raw in (None, {}, {'name': 'OTHER'}):
			with self.assertRaises(MigrationError):
				live._file_metadata_values({**self.row, 'source_file_metadata': raw}, self.plan)

	def test_unstored_source_columns_fail_even_if_empty(self):
		with patch.object(live.frappe.db, 'get_table_columns', return_value=['name']):
			with self.assertRaisesRegex(MigrationError, 'no target storage'):
				live._file_metadata_values(self.row, self.plan)

	def test_unowned_file_requires_real_app_field_reference_and_keeps_null_owner(self):
		self.plan.specs['Settings'].source_schema['fields'] = [{'fieldname': 'photo', 'fieldtype': 'Attach Image'}]
		row = {**self.row, 'attached_to_doctype': None, 'attached_to_name': None,
			'file_name': 'photo.png', 'content_hash': 'hash', 'orphan_attachment': 1,
			'app_references': [{'doctype': 'Settings', 'name': 'Settings', 'fieldname': 'photo', 'fieldtype': 'Attach Image'}]}
		row['source_file_metadata'] = {**self.raw, 'attached_to_doctype': None, 'attached_to_name': None}
		live._validate_file_metadata(row, self.plan)
		with patch.object(live.frappe.db, 'get_table_columns', return_value=list(self.raw)):
			values = live._file_metadata_values(row, self.plan)
		self.assertIsNone(values['attached_to_doctype'])
		self.assertIsNone(values['attached_to_name'])
		with self.assertRaises(MigrationError):
			live._validate_file_metadata({**row, 'app_references': []}, self.plan)
		row['app_references'][0]['fieldname'] = 'not_an_attachment'
		with self.assertRaises(MigrationError):
			live._validate_file_metadata(row, self.plan)

	def test_source_scope_selects_unowned_files_referenced_by_app_fields(self):
		helper = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/f15_source_bridge.py'))
		schema = {'Product Image': {'fields': [{'fieldname': 'image', 'fieldtype': 'Attach Image'}]}}
		files = [live.frappe._dict(name='UNOWNED', file_url='/files/photo.png')]
		from unittest.mock import Mock
		get_all = Mock(return_value=files)
		fake = SimpleNamespace(get_all=get_all, db=SimpleNamespace(sql=lambda *args, **kwargs:
			[live.frappe._dict(name='PHOTO-1', value='/files/photo.png')]))
		refs = helper['_file_reference_map'](fake, schema)
		self.assertEqual(refs['UNOWNED'][0]['doctype'], 'Product Image')
		helper['_migration_files'](fake, schema)
		self.assertEqual(get_all.call_args.kwargs['or_filters']['name'], ['in', ['UNOWNED']])
