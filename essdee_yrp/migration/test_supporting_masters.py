import json
import runpy
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from essdee_yrp.migration.engine import MigrationError
from essdee_yrp.migration.live import (
	F15SourceBridge,
	_assert_supporting_master_not_independently_edited,
	_assert_supporting_child_ownership,
	_transform_supporting_document,
	_validate_external_references,
)


class SupportingMasterTest(unittest.TestCase):
	def test_target_only_children_are_not_deleted_by_supporting_reload(self):
		field = SimpleNamespace(fieldname='links', options='Dynamic Link')
		with patch('essdee_yrp.migration.live.frappe.get_meta', return_value=SimpleNamespace(get_table_fields=lambda: [field])), \
			patch('essdee_yrp.migration.live.frappe.get_all', return_value=['TARGET-ONLY']):
			with self.assertRaisesRegex(MigrationError, 'Target-only children'):
				_assert_supporting_child_ownership({'name': 'A-1', 'links': [{'name': 'SOURCE'}]}, 'Address')

	def test_source_child_identity_cannot_take_over_an_unrelated_parent(self):
		field = SimpleNamespace(fieldname='links', options='Dynamic Link')
		with patch('essdee_yrp.migration.live.frappe.get_meta', return_value=SimpleNamespace(get_table_fields=lambda: [field])), \
			patch('essdee_yrp.migration.live.frappe.get_all', side_effect=[[], [SimpleNamespace(name='SOURCE', parent='OTHER', parenttype='Address', parentfield='links')]]):
			with self.assertRaisesRegex(MigrationError, 'identity collision'):
				_assert_supporting_child_ownership({'name': 'A-1', 'links': [{'name': 'SOURCE'}]}, 'Address')

	def meta(self, doctype):
		fields = {
			"Address": [("address_title", "Data", None), ("links", "Table", "Dynamic Link")],
			"Dynamic Link": [("link_doctype", "Link", "DocType"), ("link_name", "Dynamic Link", "link_doctype")],
		}
		return SimpleNamespace(issingle=False, fields=[SimpleNamespace(fieldname=name, fieldtype=kind, options=options)
			for name, kind, options in fields[doctype]])

	def columns(self, doctype):
		return ["name", "owner", "creation", "modified", "modified_by", "docstatus", "idx", "_user_tags"] + (
			["address_title"] if doctype == "Address" else ["parent", "parenttype", "parentfield", "link_doctype", "link_name"])

	def transform(self, document):
		with (
			patch("essdee_yrp.migration.live.frappe.get_meta", side_effect=self.meta),
			patch("essdee_yrp.migration.live.frappe.db.get_table_columns", side_effect=self.columns),
		):
			return _transform_supporting_document(document, "Address", {"Supplier": "YRP Supplier", "Location": "YRP Warehouse"})

	def test_address_reverse_links_map_doctype_without_renaming_fields_or_records(self):
		source = {"doctype": "Address", "name": "A-1", "address_title": "Billing",
			"_user_tags": "source-tag", "links": [{"doctype": "Dynamic Link", "name": "L-1",
				"link_doctype": "Supplier", "link_name": "S-1", "parenttype": "Address", "idx": 0}]}
		actual = self.transform(source)
		self.assertEqual(actual["name"], "A-1")
		self.assertEqual(actual["_user_tags"], "source-tag")
		self.assertEqual(actual["links"][0]["link_doctype"], "YRP Supplier")
		self.assertEqual(actual["links"][0]["link_name"], "S-1")
		self.assertEqual(actual["links"][0]["parenttype"], "Address")
		self.assertEqual(actual["links"][0]["idx"], 0)
		self.assertEqual(source["links"][0]["link_doctype"], "Supplier")

	def test_populated_unsupported_field_fails_without_printing_its_value(self):
		with self.assertRaises(MigrationError) as error:
			self.transform({"name": "A-1", "retired_field": "private source value"})
		self.assertIn("retired_field", str(error.exception))
		self.assertNotIn("private source value", str(error.exception))
		self.transform({"name": "A-1", "retired_field": None})

	def test_existing_native_master_or_later_edit_is_protected(self):
		source = {"name": "A-1", "creation": "2020-01-01 00:00:00", "modified": "2021-01-01 00:00:00",
			"owner": "Administrator", "modified_by": "Administrator"}
		matching = {**source, "creation": datetime(2020, 1, 1), "modified": datetime(2021, 1, 1)}
		with patch("essdee_yrp.migration.live.frappe.db.get_value", return_value=matching):
			_assert_supporting_master_not_independently_edited(source, "Address")
		with patch("essdee_yrp.migration.live.frappe.db.get_value", return_value={**matching, "modified": datetime(2026, 1, 1)}):
			with self.assertRaisesRegex(MigrationError, "independently created or edited Address"):
				_assert_supporting_master_not_independently_edited(source, "Address")

	def test_supporting_argument_batches_are_bounded(self):
		bridge = object.__new__(F15SourceBridge)
		bridge._run = Mock(return_value=[])
		list(bridge.iter_supporting_documents("Address", [f"A-{n}" for n in range(501)]))
		self.assertEqual([len(json.loads(call.args[0][-1])) for call in bridge._run.call_args_list], [250, 250, 1])

	def test_existing_direct_address_references_are_still_in_reload_scope(self):
		spec = SimpleNamespace(target="YRP Supplier", ignored_fields={}, field_map={},
			target_schema={"fields": [{"fieldname": "billing_address", "fieldtype": "Link", "options": "Address"}]})
		plan = SimpleNamespace(specs={"Supplier": spec})
		source = SimpleNamespace(iter_external_references=lambda: iter([{
			"source_doctype": "Supplier", "source_name": "S-1", "fieldname": "billing_address", "value": "A-1"}]))
		with patch("essdee_yrp.migration.live.frappe.db.exists", return_value=True):
			checked, scope = _validate_external_references(plan, source)
		self.assertEqual(checked, 1)
		self.assertEqual(scope, {"Address": {"A-1"}})

	def test_reverse_contact_scope_includes_its_selected_address(self):
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"))
		db = Mock()
		db.sql.side_effect = [[SimpleNamespace(parenttype="Address", parent="A-1"),
			SimpleNamespace(parenttype="Contact", parent="C-1")], [("A-2",)]]
		db.exists.return_value = True
		self.assertEqual(bridge["related_business_master_names"](SimpleNamespace(db=db), {"Supplier": {}}),
			{"Address": ["A-1", "A-2"], "Contact": ["C-1"]})

	def test_missing_reverse_link_parent_cannot_be_silently_discarded(self):
		bridge = runpy.run_path(str(Path(__file__).resolve().parents[2] / "scripts" / "f15_source_bridge.py"))
		db = Mock()
		db.sql.return_value = [SimpleNamespace(parenttype="Address", parent="MISSING")]
		db.exists.return_value = False
		with self.assertRaisesRegex(RuntimeError, "preserve this orphan explicitly"):
			bridge["related_business_master_names"](SimpleNamespace(db=db), {"Supplier": {}})
