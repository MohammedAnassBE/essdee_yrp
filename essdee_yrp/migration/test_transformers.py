from __future__ import annotations

import unittest

from essdee_yrp.migration.engine import MigrationError, transform_document
from essdee_yrp.migration.planner import build_schema_analysis
from essdee_yrp.patches.move_process_allowance_to_base_field import (
	choose_excess_percentage,
)


class ReviewedTransformerTest(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.plan, _payload = build_schema_analysis()

	def test_ipd_process_stage_becomes_in_and_out_stage(self):
		row = transform_document(
			{
				"doctype": "IPD Process",
				"name": "ROW-1",
				"process_name": "Printing",
				"stage": "Cut",
			},
			self.plan,
		)
		self.assertEqual((row["in_stage"], row["out_stage"]), ("Cut", "Cut"))

	def test_essdee_debit_maps_only_work_order_documents(self):
		row = transform_document(
			{
				"doctype": "Essdee Debit",
				"name": "ED-1",
				"against": "Work Order",
				"against_id": "WO-1",
				"debit_value": 100,
				"reason": "Damage",
			},
			self.plan,
		)
		self.assertEqual((row["doctype"], row["work_order"]), ("Debit", "WO-1"))
		with self.assertRaises(MigrationError):
			transform_document(
				{
					"doctype": "Essdee Debit",
					"name": "ED-2",
					"against": "Lot",
					"against_id": "LOT-1",
				},
				self.plan,
			)

	def test_purchase_order_derives_f16_fields_and_status(self):
		row = transform_document(
			{
				"doctype": "Purchase Order",
				"name": "PO-1",
				"default_delivery_location": "S-0001",
				"default_lot": "LOT-1",
				"status": "Partially Delivered",
				"open_status": "Closed",
			},
			self.plan,
		)
		self.assertEqual(row["delivery_warehouse"], "S-0001")
		self.assertEqual(row["lot"], "LOT-1")
		self.assertEqual(row["status"], "Partially Received")
		self.assertEqual(row["open_status"], "Close")

	def test_process_additional_allowance_moves_to_base_excess_field(self):
		row = transform_document(
			{
				"doctype": "Process",
				"name": "Cutting",
				"additional_allowance": 300,
			},
			self.plan,
		)
		self.assertEqual(row["wo_excess_allowed_percentage"], 300)
		self.assertNotIn("additional_allowance", row)
		self.assertEqual(choose_excess_percentage(0, 300), 300)
		self.assertEqual(choose_excess_percentage(25, 300), 25)

	def test_work_order_close_reason_maps_to_essdee_owned_field(self):
		row = transform_document(
			{
				"doctype": "Work Order",
				"name": "WO-CLOSED",
				"close_reason": "Others",
				"close_other_reason": "Production stopped",
			},
			self.plan,
		)
		self.assertEqual(row["sd_close_reason"], "Others")
		self.assertEqual(row["close_other_reason"], "Production stopped")
		self.assertNotIn("close_reason", row)

	def test_purchase_order_infers_only_an_unambiguous_header_lot(self):
		single_lot = transform_document(
			{
				"doctype": "Purchase Order",
				"name": "PO-ONE-LOT",
				"default_lot": None,
				"items": [
					{
						"doctype": "Purchase Order Item",
						"name": "ROW-1",
						"lot": "LOT-1",
					}
				],
			},
			self.plan,
		)
		self.assertEqual(single_lot["lot"], "LOT-1")

		multi_lot = transform_document(
			{
				"doctype": "Purchase Order",
				"name": "PO-MULTI-LOT",
				"default_lot": None,
				"items": [
					{
						"doctype": "Purchase Order Item",
						"name": "ROW-1",
						"lot": "LOT-1",
					},
					{
						"doctype": "Purchase Order Item",
						"name": "ROW-2",
						"lot": "LOT-2",
					},
				],
			},
			self.plan,
		)
		self.assertIsNone(multi_lot["lot"])

	def test_grn_infers_only_an_unambiguous_header_lot(self):
		single_lot = transform_document(
			{
				"doctype": "Goods Received Note",
				"name": "GRN-ONE-LOT",
				"lot": None,
				"items": [
					{
						"doctype": "Goods Received Note Item",
						"name": "ROW-1",
						"lot": "LOT-1",
					}
				],
			},
			self.plan,
		)
		self.assertEqual(single_lot["lot"], "LOT-1")

		multi_lot = transform_document(
			{
				"doctype": "Goods Received Note",
				"name": "GRN-MULTI-LOT",
				"lot": None,
				"items": [
					{
						"doctype": "Goods Received Note Item",
						"name": "ROW-1",
						"lot": "LOT-1",
					},
					{
						"doctype": "Goods Received Note Item",
						"name": "ROW-2",
						"lot": "LOT-2",
					},
				],
			},
			self.plan,
		)
		self.assertIsNone(multi_lot["lot"])

	def test_historical_grn_deliverable_lineage_is_never_invented(self):
		row = transform_document(
			{
				"doctype": "GRN Deliverable",
				"name": "LEGACY-CONSUMPTION-1",
				"item_variant": "INPUT-1",
				"quantity": 2,
				"uom": "Kg",
			},
			self.plan,
		)
		self.assertEqual(row["doctype"], "YRP GRN Deliverable")
		self.assertNotIn("goods_received_note_item", row)
		self.assertNotIn("received_item_variant", row)
		self.assertNotIn("consumption_sle", row)
		self.assertNotIn("output_receipt_sle", row)

	def test_explicit_grn_deliverable_lineage_is_preserved(self):
		row = transform_document(
			{
				"doctype": "GRN Deliverable",
				"name": "LINKED-CONSUMPTION-1",
				"item_variant": "INPUT-1",
				"quantity": 2,
				"uom": "Kg",
				"goods_received_note_item": "GRN-ITEM-1",
				"received_item_variant": "OUTPUT-1",
			},
			self.plan,
		)
		self.assertEqual(row["goods_received_note_item"], "GRN-ITEM-1")
		self.assertEqual(row["received_item_variant"], "OUTPUT-1")

	def test_stock_settings_single_uses_target_identity_and_drops_secrets(self):
		row = transform_document(
			{
				"doctype": "Stock Settings",
				"name": "Stock Settings",
				"transit_warehouse": "S-0165",
				"default_fg_lot": "FG Lot",
				"default_received_type": "Accepted",
				"default_rejected_type": "Rejected",
				"sms_old_database_password": "must-not-copy",
			},
			self.plan,
		)
		self.assertEqual(row["name"], "YRP Stock Settings")
		self.assertEqual(row["transit_warehouse"], "S-0165")
		self.assertNotIn("sms_old_database_password", row)

	def test_mrp_settings_keeps_installed_aql_and_sewing_configuration(self):
		row = transform_document(
			{
				"doctype": "MRP Settings",
				"name": "MRP Settings",
				"enable_price_validation": 1,
				"default_major_aql_level": "AQL 1.0",
				"auto_send_notifications": [
					{
						"doctype": "MRP Settings Notification Doctype List",
						"name": "ROW-1",
					}
				],
				"sewing_plan_input_orders": [
					{
						"doctype": "Sewing Plan Input Order",
						"name": "ROW-2",
					}
				],
			},
			self.plan,
		)
		self.assertEqual(row["enable_price_validation"], 1)
		self.assertEqual(row["default_major_aql_level"], "AQL 1.0")
		self.assertNotIn("auto_send_notifications", row)
		self.assertEqual(
			row["sewing_plan_input_orders"],
			[
				{
					"doctype": "Sewing Plan Input Order",
					"name": "ROW-2",
				}
			],
		)

	def test_blank_historical_purchase_invoice_against_uses_billed_details(self):
		purchase_order_invoice = transform_document(
			{
				"doctype": "Purchase Invoice",
				"name": "MPI-PO",
				"against": None,
				"pi_work_order_billed_details": [],
			},
			self.plan,
		)
		self.assertEqual(purchase_order_invoice["against"], "Purchase Order")

		work_order_invoice = transform_document(
			{
				"doctype": "Purchase Invoice",
				"name": "MPI-WO",
				"against": None,
				"pi_work_order_billed_details": [
					{
						"doctype": "PI Work Order Billed Detail",
						"name": "ROW-1",
						"work_order": "WO-1",
					}
				],
			},
			self.plan,
		)
		self.assertEqual(work_order_invoice["against"], "Work Order")

	def test_pre_category_stitching_rows_use_the_legacy_ui_default(self):
		row = transform_document(
			{
				"doctype": "Stiching Item Detail",
				"name": "ROW-1",
				"category": None,
				"stiching_attribute_value": "Sleeve",
			},
			self.plan,
		)
		self.assertEqual(row["category"], "Body")

	def test_legacy_product_item_name_uses_its_existing_style_identity(self):
		row = transform_document(
			{
				"doctype": "Product",
				"name": "34162",
				"style_no": "34162",
				"item_name": None,
			},
			self.plan,
		)
		self.assertEqual(row["item_name"], "34162")

	def test_fully_empty_ipd_process_placeholder_is_not_migrated(self):
		row = transform_document(
			{
				"doctype": "Item Production Detail",
				"name": "IPD-1",
				"ipd_processes": [
					{
						"doctype": "IPD Process",
						"name": "VALID",
						"process_name": "Printing",
						"stage": "Cut",
					},
					{
						"doctype": "IPD Process",
						"name": "EMPTY",
						"process_name": None,
						"stage": None,
					},
				],
			},
			self.plan,
		)
		self.assertEqual([child["name"] for child in row["ipd_processes"]], ["VALID"])

	def test_pre_type_lot_profit_uses_original_manual_costing_behavior(self):
		row = transform_document(
			{
				"doctype": "Lotwise Item Profit",
				"name": "ROW-1",
				"lot": "Not Applicable",
				"lot_costing_type": None,
			},
			self.plan,
		)
		self.assertEqual(row["lot_costing_type"], "Costing")

	def test_ipd_item_attribute_uses_contextual_child_doctype(self):
		row = transform_document(
			{
				"doctype": "Item Production Detail",
				"name": "IPD-1",
				"item": "ITEM-1",
				"item_attributes": [
					{
						"doctype": "Item Item Attribute",
						"name": "ROW-1",
						"attribute": "Size",
						"mapping": "MAP-1",
					}
				],
			},
			self.plan,
		)
		self.assertEqual(row["item_attributes"][0]["doctype"], "IPD Item Attribute")


if __name__ == "__main__":
	unittest.main()
