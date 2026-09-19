from __future__ import annotations

import unittest

from essdee_yrp.migration.planner import build_schema_analysis


class MigrationPlannerTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.plan, cls.payload = build_schema_analysis(
			source_site="configured-source.test",
			target_site="configured-target.test",
		)

	def test_schema_analysis_never_reads_or_writes_site_data(self):
		self.assertEqual(self.payload["source_site"], "configured-source.test")
		self.assertEqual(self.payload["target_site"], "configured-target.test")
		self.assertEqual(self.payload["mode"], "schema-only")
		self.assertFalse(self.payload["reads_site_data"])
		self.assertFalse(self.payload["writes_site_data"])

	def test_complete_source_inventory_is_classified(self):
		self.assertEqual(self.payload["source_doctypes"], 268)
		self.assertEqual(sum(self.payload["migration_kinds"].values()), 268)
		self.assertEqual(len(self.payload["doctype_details"]), 268)
		self.assertEqual(
			self.payload["migration_kinds"],
			{"custom": 4, "identity": 13, "mapped": 251},
		)

	def test_frappe_tools_configuration_is_included_but_spine_data_is_not(self):
		details = {row["source_doctype"]: row for row in self.payload["doctype_details"]}
		self.assertTrue(
			{
				"Document Scanner Settings",
				"Document Scanner Settings Items",
				"Document Scanner Server Setting",
				"Log File Downloader",
			}.issubset(details)
		)
		for excluded_doctype in (
			"Message Log",
			"Spine Consumer Config",
			"Spine Consumer Handler Mapping",
			"Spine Producer Config",
			"Spine Producer Handler Mapping",
		):
			self.assertNotIn(excluded_doctype, details)

	def test_approved_frappe_live_data_has_target_value_audit_schemas(self):
		for doctype in (
			"Address",
			"Contact",
			"Dynamic Link",
			"Contact Email",
			"Contact Phone",
			"Role",
			"Module Profile",
			"Block Module",
			"User",
			"Has Role",
			"User Social Login",
			"Custom DocPerm",
			"System Settings",
			"Workspace",
			"Workspace Shortcut",
		):
			self.assertIn(doctype, self.plan.target_schemas)
		# They are a selective live-data phase, not whole-table reset routes.
		self.assertNotIn("Address", self.plan.specs)
		self.assertNotIn("Contact", self.plan.specs)
		self.assertNotIn("User", self.plan.specs)
		self.assertNotIn("Custom DocPerm", self.plan.specs)

	def test_known_renames_appear_in_doctype_details(self):
		details = {row["source_doctype"]: row for row in self.payload["doctype_details"]}
		self.assertEqual(details["SMS Settings"]["target_doctype"], "SMS Settings")
		self.assertEqual(details["Department User"]["target_doctype"], "YRP Department User")
		self.assertEqual(details["GRN Item Type"]["target_doctype"], 'YRP Received Type')
		self.assertEqual(details["GRN Deliverable"]["target_doctype"], 'SD YRP GRN Deliverable')
		self.assertEqual(details["Lot Transfer Item"]["target_doctype"], 'SD YRP Lot Transfer Item')
		self.assertEqual(details["Stock Settings"]["target_doctype"], 'YRP Stock Settings')
		self.assertEqual(details["Purchase Order Lot"]["target_doctype"], 'SD YRP Lot MultiSelect')
		self.assertEqual(
			details["GRN Item Type"]["field_map"],
			{"grn_type": "received_type_name"},
		)
		self.assertEqual(details["Vendor Bill Tracking"]["target_doctype"], 'YRP Bill Tracking')

	def test_migration_targets_never_contain_a_redundant_yrp_segment(self):
		targets = {row["target_doctype"] for row in self.payload["doctype_details"]}
		self.assertEqual(sorted(target for target in targets if "YRP YRP" in target), [])

	def test_reviewed_mappings_resolve_every_schema_blocker(self):
		self.assertTrue(self.plan.ready, self.plan.issues)
		self.assertEqual(self.payload["issue_count"], 0)
		self.assertEqual(self.payload["issues"], [])

	def test_contextual_and_value_mappings_are_auditable(self):
		details = {row["source_doctype"]: row for row in self.payload["doctype_details"]}
		self.assertEqual(
			details["Item Production Detail"]["table_option_map"],
			{"item_attributes": 'YRP IPD Item Attribute'},
		)
		self.assertEqual(
			details["Vendor Bill Tracking"]["field_map"],
			{
				"mrp_purchase_invoice": "purchase_invoice",
				"purchase_invoice": "erp_purchase_invoice",
				"vendor_bill_tracking_history": "bill_tracking_history",
			},
		)
		self.assertNotIn("description", details["Item"]["ignored_fields"])
		self.assertNotIn(
			"description", details["Item Production Detail"]["ignored_fields"]
		)


if __name__ == "__main__":
	unittest.main()
