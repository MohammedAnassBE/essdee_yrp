from __future__ import annotations

import base64
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from essdee_yrp.migration.engine import MigrationError
from essdee_yrp.migration.live import (
	F15SourceBridge,
	FrappeBulkTarget,
	_decode_and_validate_file_payload,
	_validate_required_target_values,
)


class MigrationLiveAdapterTest(unittest.TestCase):
	def test_selected_attachment_bridge_arguments_are_explicit(self):
		bridge = F15SourceBridge()
		with patch.object(bridge, "_run", return_value=iter([{"file_count": 2}])) as run:
			self.assertEqual(bridge.file_status(names=["FILE-2", "FILE-1"])["file_count"], 2)
		run.assert_called_once_with(
			["file-status", "--names-json", '["FILE-1", "FILE-2"]']
		)

	def test_series_bridge_is_fixed_to_the_source_series_command(self):
		bridge = F15SourceBridge()
		with patch.object(
			bridge,
			"_run",
			return_value=iter([{"name": "WO-", "current": 42}]),
		) as run:
			self.assertEqual(
				list(bridge.iter_series()),
				[{"name": "WO-", "current": 42}],
			)
		run.assert_called_once_with(["series"])

		with patch.object(bridge, "_run", return_value=iter([])) as run:
			self.assertEqual(
				list(
					bridge.iter_files(
						names=["FILE-2", "FILE-1"], allow_missing=True
					)
				),
				[],
			)
		run.assert_called_once_with(
			[
				"files",
				"--names-json",
				'["FILE-1", "FILE-2"]',
				"--allow-missing",
			]
		)

	def test_attachment_transport_is_byte_and_hash_checked(self):
		content = b"historical attachment bytes\x00\xff"
		row = {
			"name": "FILE-1",
			"file_size": len(content),
			"content_hash": hashlib.md5(content, usedforsecurity=False).hexdigest(),
			"content_base64": base64.b64encode(content).decode("ascii"),
		}
		self.assertEqual(_decode_and_validate_file_payload(row), content)
		row["content_hash"] = "incorrect"
		with self.assertRaisesRegex(MigrationError, "hash mismatch"):
			_decode_and_validate_file_payload(row)

	def test_single_child_tables_are_replaced_with_target_parent_identity(self):
		meta = SimpleNamespace(
			name="MRP Settings",
			get_table_fields=lambda: [
				SimpleNamespace(fieldname="routes", options="MRP Settings Route")
			],
		)
		target = FrappeBulkTarget()
		bulk_rows = []
		with (
			patch("essdee_yrp.migration.live.frappe.db.delete") as delete,
			patch.object(target, "_bulk_upsert", side_effect=lambda doctype, rows: bulk_rows.extend(rows)),
		):
			target._replace_child_tables(
				meta,
				[
					{
						"doctype": "MRP Settings",
						"name": "MRP Settings",
						"routes": [
							{
								"doctype": "MRP Settings Route",
								"name": "ROW-1",
								"route": "Goods Received Note",
							}
						],
					}
				],
			)

		delete.assert_called_once_with(
			"MRP Settings Route",
			{
				"parenttype": "MRP Settings",
				"parentfield": "routes",
				"parent": ["in", ["MRP Settings"]],
			},
		)
		self.assertEqual(bulk_rows[0]["parenttype"], "MRP Settings")
		self.assertEqual(bulk_rows[0]["parentfield"], "routes")
		self.assertEqual(bulk_rows[0]["parent"], "MRP Settings")

	def test_single_required_value_can_be_preserved_from_target(self):
		schema = {
			"name": "IPD Settings",
			"issingle": 1,
			"fields": [
				{"fieldname": "default_knitting_process", "fieldtype": "Link", "reqd": 1}
			],
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_single_value",
			return_value="Knitting",
		):
			document = {"doctype": "IPD Settings", "name": "IPD Settings"}
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["default_knitting_process"], "Knitting")

	def test_required_value_can_be_preserved_from_existing_target_document(self):
		schema = {
			"name": "Item",
			"fields": [
				{"fieldname": "item_group", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {"doctype": "Item", "name": "Legacy Item", "item_group": None}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value="All Item Groups",
		):
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["item_group"], "All Item Groups")

	def test_purchase_invoice_item_group_is_derived_from_item_variant(self):
		schema = {
			"name": "Purchase Invoice Item",
			"fields": [
				{"fieldname": "item_group", "fieldtype": "Data", "reqd": 1}
			],
		}
		document = {
			"doctype": "Purchase Invoice Item",
			"name": "ROW-1",
			"item": "VARIANT-1",
			"item_group": None,
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			side_effect=["ITEM-1", "Fabric"],
		):
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["item_group"], "Fabric")

	def test_packaging_lot_bom_process_is_derived_from_item_group(self):
		schema = {
			"name": "Lot BOM",
			"fields": [
				{"fieldname": "process_name", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": "Lot BOM",
			"name": "ROW-1",
			"item_name": "TOP-BOX-VARIANT",
			"process_name": None,
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			side_effect=["TOP-BOX", "Purchase Accessories"],
		):
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["process_name"], "Packing")

	def test_packaging_lot_bom_uom_is_derived_from_item_master(self):
		schema = {
			"name": "Lot BOM",
			"fields": [{"fieldname": "uom", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": "Lot BOM",
			"name": "ROW-1",
			"item_name": "TOP-BOX-VARIANT",
			"uom": None,
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			side_effect=["TOP-BOX", "Nos"],
		):
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["uom"], "Nos")

	def test_purchase_order_item_uom_is_derived_from_item_master(self):
		schema = {
			"name": "Purchase Order Item",
			"fields": [{"fieldname": "uom", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": "Purchase Order Item",
			"name": "ROW-1",
			"item_variant": "LABEL-VARIANT",
			"uom": None,
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			side_effect=["LABEL", "Nos"],
		):
			preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["uom"], "Nos")

	def test_source_item_reference_resolves_uom_before_target_write(self):
		schema = {
			"name": "Purchase Order Item",
			"fields": [{"fieldname": "uom", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": "Purchase Order Item",
			"name": "ROW-NEWER-THAN-TARGET",
			"item_variant": "NEW-VARIANT",
			"uom": None,
		}
		references = {
			"variant_to_item": {"NEW-VARIANT": "NEW-ITEM"},
			"item_defaults": {"NEW-ITEM": "Nos"},
		}
		with patch("essdee_yrp.migration.live.frappe.db.get_value") as get_value:
			preserved = _validate_required_target_values(
				document, schema, reference_data=references
			)
		get_value.assert_not_called()
		self.assertEqual(preserved, 1)
		self.assertEqual(document["uom"], "Nos")

	def test_historical_process_cost_blanks_are_preserved_and_audited(self):
		schema = {
			"name": "Process Cost",
			"fields": [
				{"fieldname": "supplier", "fieldtype": "Link", "reqd": 1},
				{"fieldname": "lot", "fieldtype": "Link", "reqd": 1},
			],
		}
		document = {
			"doctype": "Process Cost",
			"name": "PC-00001",
			"creation": "2025-01-29 14:14:37",
			"supplier": None,
			"lot": None,
		}
		audit = {}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value=None,
		):
			preserved = _validate_required_target_values(document, schema, audit)
		self.assertEqual(preserved, 0)
		self.assertEqual(
			audit,
			{"Process Cost.supplier": 1, "Process Cost.lot": 1},
		)

	def test_post_cutoff_process_cost_blank_still_fails(self):
		schema = {
			"name": "Process Cost",
			"fields": [
				{"fieldname": "supplier", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": "Process Cost",
			"name": "PC-NEW",
			"creation": "2026-01-01 00:00:00",
			"supplier": None,
		}
		with (
			patch(
				"essdee_yrp.migration.live.frappe.db.get_value",
				return_value=None,
			),
			self.assertRaisesRegex(Exception, "supplier"),
		):
			_validate_required_target_values(document, schema)

	def test_historical_multi_lot_purchase_order_blank_is_audited(self):
		schema = {
			"name": "Purchase Order",
			"fields": [{"fieldname": "lot", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": "Purchase Order",
			"name": "PO-2324-0138",
			"creation": "2023-04-22 17:09:45",
			"lot": None,
		}
		audit = {}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value=None,
		):
			preserved = _validate_required_target_values(document, schema, audit)
		self.assertEqual(preserved, 0)
		self.assertEqual(audit, {"Purchase Order.lot": 1})

	def test_historical_multi_lot_grn_blank_is_audited(self):
		schema = {
			"name": "Goods Received Note",
			"fields": [{"fieldname": "lot", "fieldtype": "Link", "reqd": 1}],
		}
		document = {
			"doctype": "Goods Received Note",
			"name": "GRN-2526-00001",
			"creation": "2025-04-01 10:00:00",
			"lot": None,
		}
		audit = {}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value=None,
		):
			preserved = _validate_required_target_values(document, schema, audit)
		self.assertEqual(preserved, 0)
		self.assertEqual(audit, {"Goods Received Note.lot": 1})

	def test_cut_panel_warehouse_is_recovered_from_source_references(self):
		schema = {
			"name": "Cut Panel Movement",
			"fields": [
				{"fieldname": "from_warehouse", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": "Cut Panel Movement",
			"name": "CPM-2505-00010",
			"creation": "2025-05-27 18:24:23",
			"from_warehouse": None,
		}
		references = {
			"cut_panel_from_warehouse": {"CPM-2505-00010": "S-0164"}
		}
		preserved = _validate_required_target_values(
			document, schema, reference_data=references
		)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["from_warehouse"], "S-0164")

	def test_blank_legacy_stock_received_type_uses_configured_default(self):
		schema = {
			"name": "Work Order Deliverables",
			"fields": [
				{"fieldname": "received_type", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": "Work Order Deliverables",
			"name": "ROW-1",
			"received_type": None,
		}
		preserved = _validate_required_target_values(document, schema)
		self.assertEqual(preserved, 1)
		self.assertEqual(document["received_type"], "Accepted")

	def test_unrecoverable_pre_field_cut_panel_warehouse_is_audited(self):
		schema = {
			"name": "Cut Panel Movement",
			"fields": [
				{"fieldname": "from_warehouse", "fieldtype": "Link", "reqd": 1}
			],
		}
		document = {
			"doctype": "Cut Panel Movement",
			"name": "CPM-2503-00001",
			"creation": "2025-03-25 18:16:12",
			"from_warehouse": None,
		}
		audit = {}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_value",
			return_value=None,
		):
			preserved = _validate_required_target_values(document, schema, audit)
		self.assertEqual(preserved, 0)
		self.assertEqual(audit, {"Cut Panel Movement.from_warehouse": 1})

	def test_single_required_value_still_fails_when_both_sites_are_empty(self):
		schema = {
			"name": "IPD Settings",
			"issingle": 1,
			"fields": [
				{"fieldname": "default_knitting_process", "fieldtype": "Link", "reqd": 1}
			],
		}
		with patch(
			"essdee_yrp.migration.live.frappe.db.get_single_value",
			return_value=None,
		):
			with self.assertRaisesRegex(Exception, "default_knitting_process"):
				_validate_required_target_values(
					{"doctype": "IPD Settings", "name": "IPD Settings"}, schema
				)


if __name__ == "__main__":
	unittest.main()
