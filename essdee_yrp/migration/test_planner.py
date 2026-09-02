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
		self.assertEqual(self.payload["source_doctypes"], 263)
		self.assertEqual(sum(self.payload["migration_kinds"].values()), 263)
		self.assertEqual(len(self.payload["doctype_details"]), 263)
		self.assertEqual(
			self.payload["migration_kinds"],
			{"custom": 3, "identity": 1, "mapped": 259},
		)

	def test_known_renames_appear_in_doctype_details(self):
		details = {row["source_doctype"]: row for row in self.payload["doctype_details"]}
		self.assertEqual(details["GRN Item Type"]["target_doctype"], 'YRP Received Type')
		self.assertEqual(details["GRN Deliverable"]["target_doctype"], 'SD YRP YRP GRN Deliverable')
		self.assertEqual(details["Purchase Order Lot"]["target_doctype"], 'SD YRP Lot MultiSelect')
		self.assertEqual(
			details["GRN Item Type"]["field_map"],
			{"grn_type": "received_type_name"},
		)
		self.assertEqual(details["Vendor Bill Tracking"]["target_doctype"], 'YRP Bill Tracking')

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
		self.assertIn("description", details["Item"]["ignored_fields"])
		self.assertIn(
			"description", details["Item Production Detail"]["ignored_fields"]
		)


if __name__ == "__main__":
	unittest.main()
