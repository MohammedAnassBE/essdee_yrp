import json
from pathlib import Path

import frappe
from frappe.model import no_value_fields
from frappe.model.base_document import get_controller
from frappe.tests.utils import FrappeTestCase


class TestMRPSchemaStructure(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		root = Path(frappe.get_app_path("essdee_yrp", "essdee_yrp", "doctype"))
		cls.schemas = {}
		for path in root.glob("*/*.json"):
			schema = json.loads(path.read_text())
			cls.schemas[schema["name"]] = schema

	def test_json_field_order_matches_live_doctype(self):
		for name, schema in self.schemas.items():
			with self.subTest(doctype=name):
				doctype = frappe.get_doc("DocType", name)
				actual = [field.fieldname for field in sorted(doctype.fields, key=lambda field: field.idx)]
				self.assertEqual(doctype.module, "Essdee YRP")
				self.assertEqual(bool(doctype.istable), bool(schema.get("istable")))
				self.assertEqual(actual, schema.get("field_order", []))

	def test_all_controllers_import(self):
		for name in self.schemas:
			with self.subTest(doctype=name):
				self.assertIsNotNone(get_controller(name))

	def test_finishing_dispatch_item_keeps_packing_trace_fields(self):
		meta = frappe.get_meta("Finishing Plan Dispatch Item", cached=False)
		expected = {
			"packing_source": "Data",
			"packing_piece_quantity": "Float",
		}
		for fieldname, fieldtype in expected.items():
			field = meta.get_field(fieldname)
			self.assertIsNotNone(field, fieldname)
			self.assertEqual(field.fieldtype, fieldtype)
			self.assertEqual(field.hidden, 1)
			self.assertEqual(field.read_only, 1)

	def test_link_and_table_targets_are_valid(self):
		for name, schema in self.schemas.items():
			for field in schema.get("fields", []):
				if field.get("fieldtype") not in {"Link", "Table", "Table MultiSelect"}:
					continue
				if not field.get("options"):
					continue
				with self.subTest(doctype=name, fieldname=field["fieldname"]):
					target_is_table = frappe.db.get_value("DocType", field["options"], "istable")
					self.assertIsNotNone(target_is_table)
					if field["fieldtype"] in {"Table", "Table MultiSelect"}:
						self.assertTrue(target_is_table)
					else:
						self.assertFalse(target_is_table)

	def test_physical_columns_exist(self):
		for name, schema in self.schemas.items():
			if schema.get("issingle") or schema.get("is_virtual"):
				continue
			columns = set(frappe.db.get_table_columns(name))
			for field in schema.get("fields", []):
				if field["fieldtype"] in no_value_fields:
					continue
				with self.subTest(doctype=name, fieldname=field["fieldname"]):
					self.assertIn(field["fieldname"], columns)
