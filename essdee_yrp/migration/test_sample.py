from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from essdee_yrp.migration.live import F15SourceBridge
from essdee_yrp.migration.sample import QueryOnlySampleTarget, _same_db_value


class TestQueryOnlySample(UnitTestCase):
	def test_source_bridge_caps_export_at_the_source(self):
		bridge = F15SourceBridge()
		with patch.object(bridge, "_run", return_value=iter(())) as run:
			list(bridge.iter_documents("Lot", batch_size=20, limit=20))
		run.assert_called_once_with(
			["export", "--doctype", "Lot", "--batch-size", "20", "--limit", "20"]
		)

	def test_source_bridge_returns_effective_live_schemas(self):
		bridge = F15SourceBridge()
		rows = iter(
			[
				{
					"kind": "schema",
					"schema": {"name": "Lot", "doctype": "DocType", "fields": []},
				}
			]
		)
		with patch.object(bridge, "_run", return_value=rows) as run:
			self.assertEqual(set(bridge.schemas()), {"Lot"})
		run.assert_called_once_with(["schemas"])

	def test_parent_upsert_never_passes_password_payload_to_sql(self):
		meta = frappe._dict(
			issingle=False,
			get_table_fields=lambda: [],
		)
		target = QueryOnlySampleTarget()
		with (
			patch.object(frappe, "get_meta", return_value=meta),
			patch.object(target, "_bulk_upsert") as bulk_upsert,
			patch.object(target, "_replace_child_tables_sql"),
		):
			target.upsert_batch(
				'SD YRP MRP Settings',
				[
					{
						"doctype": 'SD YRP MRP Settings',
						"name": 'SD YRP MRP Settings',
						"value": "kept",
						"__migration_passwords": {"api_secret": "must-not-enter-parent-table"},
					}
				],
			)
		self.assertEqual(
			bulk_upsert.call_args.args,
			('SD YRP MRP Settings', [{"name": 'SD YRP MRP Settings', "value": "kept"}]),
		)

	def test_numeric_and_json_sql_round_trip_comparison(self):
		self.assertTrue(_same_db_value(1, 1.0, "Float"))
		self.assertTrue(_same_db_value({"b": 2, "a": 1}, '{"a":1,"b":2}', "JSON"))

	def test_sample_module_has_no_document_write_api(self):
		source = (Path(__file__).resolve().parent / "sample.py").read_text()
		self.assertNotIn("frappe.get_doc", source)
		self.assertNotIn(".insert(", source)
		self.assertNotIn(".save(", source)


if __name__ == "__main__":
	import unittest

	unittest.main()
