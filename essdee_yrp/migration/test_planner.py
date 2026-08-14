from __future__ import annotations

import unittest

from essdee_yrp.migration.planner import SOURCE_SITE, TARGET_SITE, build_schema_analysis


class MigrationPlannerTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.plan, cls.payload = build_schema_analysis()

	def test_schema_analysis_never_reads_or_writes_site_data(self):
		self.assertEqual(SOURCE_SITE, "mrp3.site")
		self.assertEqual(TARGET_SITE, "essdee_yrp.site")
		self.assertEqual(self.payload["mode"], "schema-only")
		self.assertFalse(self.payload["reads_site_data"])
		self.assertFalse(self.payload["writes_site_data"])

	def test_complete_source_inventory_is_classified(self):
		self.assertEqual(self.payload["source_doctypes"], 260)
		self.assertEqual(sum(self.payload["migration_kinds"].values()), 260)
		self.assertEqual(len(self.payload["doctype_details"]), 260)
		self.assertEqual(
			self.payload["migration_kinds"],
			{"custom": 3, "identity": 225, "mapped": 32},
		)

	def test_known_renames_appear_in_doctype_details(self):
		details = {row["source_doctype"]: row for row in self.payload["doctype_details"]}
		self.assertEqual(details["GRN Item Type"]["target_doctype"], "Received Type")
		self.assertEqual(details["GRN Deliverable"]["target_doctype"], "YRP GRN Deliverable")
		self.assertEqual(details["Purchase Order Lot"]["target_doctype"], "Lot MultiSelect")
		self.assertEqual(
			details["GRN Item Type"]["field_map"],
			{"grn_type": "received_type_name"},
		)
		self.assertEqual(details["Vendor Bill Tracking"]["target_doctype"], "Bill Tracking")

	def test_reviewed_mappings_resolve_every_schema_blocker(self):
		self.assertTrue(self.plan.ready, self.plan.issues)
		self.assertEqual(self.payload["issue_count"], 0)
		self.assertEqual(self.payload["issues"], [])

	def test_contextual_and_value_mappings_are_auditable(self):
		details = {row["source_doctype"]: row for row in self.payload["doctype_details"]}
		self.assertEqual(
			details["Item Production Detail"]["table_option_map"],
			{"item_attributes": "IPD Item Attribute"},
		)
		self.assertEqual(
			details["Vendor Bill Tracking"]["field_map"],
			{
				"mrp_purchase_invoice": "purchase_invoice",
				"purchase_invoice": "erp_purchase_invoice",
				"vendor_bill_tracking_history": "bill_tracking_history",
			},
		)


if __name__ == "__main__":
	unittest.main()
