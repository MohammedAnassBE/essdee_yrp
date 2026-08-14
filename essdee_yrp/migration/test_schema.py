from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from essdee_yrp.migration.schema import (
	SchemaError,
	apply_custom_field_fixture,
	apply_declared_stock_dimensions,
	apply_property_setter_fixture,
	load_schema_index,
)


class SchemaTest(unittest.TestCase):
	def test_schema_loading_and_fixture_overlays_are_filesystem_only(self):
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory)
			(root / "thing.json").write_text(
				json.dumps(
					{
						"doctype": "DocType",
						"name": "Thing",
						"fields": [{"fieldname": "title", "fieldtype": "Data"}],
					}
				)
			)
			custom_fields = root / "custom_fields.json"
			custom_fields.write_text(
				json.dumps(
					[
						{
							"doctype": "Custom Field",
							"dt": "Thing",
							"fieldname": "received_type",
							"fieldtype": "Link",
							"options": "Received Type",
						}
					]
				)
			)
			property_setters = root / "property_setters.json"
			property_setters.write_text(
				json.dumps(
					[
						{
							"doc_type": "Thing",
							"field_name": "title",
							"property": "fieldtype",
							"property_type": "Data",
							"value": "Small Text",
						}
					]
				)
			)

			schemas = load_schema_index(root)
			schemas = apply_custom_field_fixture(schemas, custom_fields)
			schemas = apply_property_setter_fixture(schemas, property_setters)
			fields = {row["fieldname"]: row for row in schemas["Thing"]["fields"]}
			self.assertEqual(fields["title"]["fieldtype"], "Small Text")
			self.assertEqual(fields["received_type"]["options"], "Received Type")

	def test_conflicting_duplicate_schemas_fail_closed(self):
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory)
			(root / "a").mkdir()
			(root / "b").mkdir()
			(root / "a" / "thing.json").write_text(
				json.dumps({"doctype": "DocType", "name": "Thing", "fields": []})
			)
			(root / "b" / "thing.json").write_text(
				json.dumps(
					{
						"doctype": "DocType",
						"name": "Thing",
						"fields": [{"fieldname": "value", "fieldtype": "Data"}],
					}
				)
			)
			with self.assertRaises(SchemaError):
				load_schema_index(root)

	def test_code_declared_dimensions_are_overlaid_without_a_site(self):
		schemas = {
			"Stock Row": {"name": "Stock Row", "fields": []},
			"Operational": {"name": "Operational", "fields": []},
		}
		result = apply_declared_stock_dimensions(
			schemas,
			dimensions=[
				{
					"dimension_doctype": "Lot",
					"fieldname": "lot",
					"is_production_group": 1,
				}
			],
			stock_doctypes=["Stock Row"],
			operational_doctypes=["Operational"],
		)
		for doctype in ("Stock Row", "Operational"):
			self.assertEqual(result[doctype]["fields"][0]["options"], "Lot")
		self.assertEqual(schemas["Stock Row"]["fields"], [])


if __name__ == "__main__":
	unittest.main()
