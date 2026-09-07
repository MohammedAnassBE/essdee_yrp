import runpy
import unittest
from pathlib import Path
from types import SimpleNamespace

import frappe


class SourceFrameworkScopeTest(unittest.TestCase):
	def test_indirect_history_and_its_files_are_selected_without_side_effects(self):
		helper = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/f15_framework_archive.py'))
		fields = {'Report': 'ref_doctype', 'Data Import': 'reference_doctype', 'Number Card': 'document_type'}
		columns = {doctype: ['name', field] for doctype, field in fields.items()}
		columns.update({'Prepared Report': ['name', 'report_name'], 'Auto Email Report': ['name', 'report'],
			'Data Import Log': ['name', 'data_import'], 'Number Card Link': ['name', 'card']})
		def sql(statement, params=()):
			if 'SELECT DISTINCT parent FROM tabDocField' in statement:
				return [(doctype,) for doctype in fields]
			if 'SELECT DISTINCT dt FROM' in statement:
				return []
			if 'SELECT DISTINCT folder FROM tabFile' in statement:
				return []
			self.fail('Unexpected non-read-only/scoped SQL')
		def meta(doctype):
			field = fields.get(doctype)
			return SimpleNamespace(name=doctype, fields=[SimpleNamespace(fieldname=field,
				fieldtype='Link', options='DocType')] if field else [], get_table_fields=lambda: [])
		frappe = SimpleNamespace(db=SimpleNamespace(sql=sql, table_exists=lambda dt: dt in columns,
			get_table_columns=lambda dt: columns[dt], exists=lambda *args: True), get_meta=meta)
		scope = helper['build_scope'](frappe, {'Supplier': {}}, (), {})
		for doctype in ('Prepared Report', 'Auto Email Report', 'Data Import Log', 'Number Card Link'):
			self.assertIn(doctype, scope)
			self.assertIn(doctype, scope['File'][1])
		self.assertIn('`report_name` IN (SELECT name FROM `tabReport`', scope['Prepared Report'][0])

	def test_folder_ancestors_include_roots_and_missing_ancestor_fails(self):
		helper = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'scripts/f15_framework_archive.py'))
		folders = {'Home/product': 'Home', 'Home': None}
		def sql(statement, params=(), **kwargs):
			if 'SELECT DISTINCT folder FROM tabFile' in statement:
				return [('Home/product',)]
			if 'SELECT name,folder,is_folder FROM tabFile' in statement:
				return [frappe._dict(name=name, folder=folders[name], is_folder=1)
					for name in params[0] if name in folders]
			return []
		fake = SimpleNamespace(db=SimpleNamespace(sql=sql))
		scope = helper['build_scope'](fake, {'Supplier': {}}, (), {})
		self.assertEqual(scope['File'][1][-1], ('Home', 'Home/product'))
		del folders['Home']
		with self.assertRaisesRegex(RuntimeError, 'missing/non-folder'):
			helper['build_scope'](fake, {'Supplier': {}}, (), {})
