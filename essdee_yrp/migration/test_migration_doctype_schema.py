from __future__ import annotations

import json
import unittest
from pathlib import Path


DOCTYPE_ROOT = Path(__file__).resolve().parents[1] / "essdee_yrp" / "doctype"


class MigrationDocTypeSchemaTest(unittest.TestCase):
	def test_parent_is_essdee_owned_and_system_manager_only(self):
		path = DOCTYPE_ROOT / "mrp_data_migration" / "mrp_data_migration.json"
		schema = json.loads(path.read_text())
		self.assertEqual(schema["name"], "MRP Data Migration")
		self.assertEqual(schema["module"], "Essdee YRP")
		self.assertEqual([row["role"] for row in schema["permissions"]], ["System Manager"])
		fields = {row["fieldname"]: row for row in schema["fields"]}
		self.assertEqual(fields["source_site"]["default"], "mrp3.site")
		self.assertEqual(fields["target_site"]["default"], "essdee_yrp.site")
		self.assertEqual(fields["adapter_status"]["default"], "Live Migration Ready")
		self.assertEqual(fields["migration_details"]["options"], "MRP Data Migration Detail")

	def test_detail_is_read_only_child_audit_table(self):
		path = DOCTYPE_ROOT / "mrp_data_migration_detail" / "mrp_data_migration_detail.json"
		schema = json.loads(path.read_text())
		self.assertEqual(schema["name"], "MRP Data Migration Detail")
		self.assertTrue(schema["istable"])
		self.assertEqual(schema["module"], "Essdee YRP")
		self.assertEqual(schema["permissions"], [])
		data_fields = [
			row
			for row in schema["fields"]
			if row["fieldtype"] not in {"Section Break", "Column Break"}
		]
		self.assertTrue(all(row.get("read_only") for row in data_fields))


if __name__ == "__main__":
	unittest.main()
