from __future__ import annotations

import json
import unittest
from pathlib import Path

from essdee_yrp.essdee_yrp.doctype.sd_yrp_mrp_data_migration.sd_yrp_mrp_data_migration import (
	is_target_reset_ready,
)


DOCTYPE_ROOT = Path(__file__).resolve().parents[1] / "essdee_yrp" / "doctype"
APP_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_ROOT = DOCTYPE_ROOT / "sd_yrp_mrp_data_migration"
MIGRATION_DETAIL_ROOT = DOCTYPE_ROOT / "sd_yrp_mrp_data_migration_detail"
CUTTING_LAYSHEET_PLANNER_ROOT = DOCTYPE_ROOT / "sd_yrp_cutting_laysheet_planner"


class MigrationDocTypeSchemaTest(unittest.TestCase):
	def test_failed_reset_can_preview_and_retry_only_the_same_action(self):
		self.assertTrue(is_target_reset_ready("Dry Run Complete", "Dry Run"))
		self.assertTrue(is_target_reset_ready("Failed", "Reset Target"))
		self.assertFalse(is_target_reset_ready("Failed", "Dry Run"))
		self.assertFalse(is_target_reset_ready("Failed", "Migrate"))
		self.assertFalse(is_target_reset_ready("Running", "Reset Target"))

	def test_live_runner_contains_no_local_environment_or_record_whitelist(self):
		paths = (
			Path(__file__).with_name("config.py"),
			Path(__file__).with_name("live.py"),
			APP_ROOT / "scripts" / "f15_source_bridge.py",
		)
		forbidden = (
			"/home/anas/frappe-15",
			"mrp3.site",
			"essdee_yrp.site",
			"AUDITED_HISTORICAL_BROKEN_LINKS",
		)
		for path in paths:
			contents = path.read_text()
			for value in forbidden:
				self.assertNotIn(value, contents, f"{value!r} is hardcoded in {path}")

	def test_parent_is_essdee_owned_and_system_manager_only(self):
		path = MIGRATION_ROOT / "sd_yrp_mrp_data_migration.json"
		schema = json.loads(path.read_text())
		self.assertEqual(schema["name"], 'SD YRP MRP Data Migration')
		self.assertEqual(schema["module"], "Essdee YRP")
		self.assertEqual([row["role"] for row in schema["permissions"]], ["System Manager"])
		fields = {row["fieldname"]: row for row in schema["fields"]}
		self.assertNotIn("source_bench", fields)
		self.assertNotIn("default", fields["source_site"])
		self.assertNotIn("default", fields["target_site"])
		self.assertEqual(
			fields["adapter_status"]["default"], "Configured Local-Bench Source"
		)
		self.assertEqual(fields["migration_details"]["options"], 'SD YRP MRP Data Migration Detail')
		self.assertEqual(fields["allow_missing_source_blobs"]["default"], "0")
		controller = (MIGRATION_ROOT / "sd_yrp_mrp_data_migration.py").read_text()
		self.assertIn(
			"allow_missing_files=bool(self.allow_missing_source_blobs)",
			controller,
		)
		self.assertIn("def reset_target", controller)
		self.assertIn("def get_reset_preview", controller)
		self.assertIn('expected = f"RESET {self.target_site}"', controller)
		self.assertIn('allowed_statuses={"Reset Complete", "Failed"}', controller)
		self.assertIn("Reset Complete", fields["status"]["options"])
		self.assertIn("Reset Target", fields["last_action"]["options"])
		client = (MIGRATION_ROOT / "sd_yrp_mrp_data_migration.js").read_text()
		self.assertIn("Reset Target Data", client)
		self.assertIn("preview.parent_rows", client)
		self.assertIn("values.confirmation", client)

	def test_new_desk_run_loads_required_read_only_connection_fields(self):
		controller = (MIGRATION_ROOT / "sd_yrp_mrp_data_migration.py").read_text()
		client = (MIGRATION_ROOT / "sd_yrp_mrp_data_migration.js").read_text()
		self.assertIn("def get_connection_defaults", controller)
		self.assertIn('frappe.only_for("System Manager")', controller)
		self.assertIn("get_connection_defaults", client)
		self.assertNotIn('.prop("disabled"', client)
		for fieldname in ("source_site", "source_app", "target_site", "target_apps"):
			self.assertIn(f'"{fieldname}"', controller)

	def test_detail_is_read_only_child_audit_table(self):
		path = MIGRATION_DETAIL_ROOT / "sd_yrp_mrp_data_migration_detail.json"
		schema = json.loads(path.read_text())
		self.assertEqual(schema["name"], 'SD YRP MRP Data Migration Detail')
		self.assertTrue(schema["istable"])
		self.assertEqual(schema["module"], "Essdee YRP")
		self.assertEqual(schema["permissions"], [])
		data_fields = [
			row
			for row in schema["fields"]
			if row["fieldtype"] not in {"Section Break", "Column Break"}
		]
		self.assertTrue(all(row.get("read_only") for row in data_fields))

	def test_cutting_laysheet_planner_tracks_live_source_identity_fields(self):
		path = CUTTING_LAYSHEET_PLANNER_ROOT / "sd_yrp_cutting_laysheet_planner.json"
		schema = json.loads(path.read_text())
		fields = {row["fieldname"]: row for row in schema["fields"]}
		self.assertEqual(fields["lot"]["options"], 'SD YRP Lot')
		self.assertEqual(fields["item"]["options"], 'YRP Item')
		self.assertEqual(fields["description"]["fieldtype"], "Small Text")
		self.assertTrue(fields["description"]["reqd"])


if __name__ == "__main__":
	unittest.main()
