from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.sd_yrp_sync import (
	PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE,
	PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE,
	PRODUCTION_ORDER_GRID_ATTRIBUTE,
	SYNC_DOCTYPES,
	filter_doc_fields,
	handle_sd_yrp_message,
	map_production_ordered_rows,
	upsert_doc,
)
from essdee_yrp.setup import ensure_yrp_production_order_settings


class TestSDYRPSyncSetup(IntegrationTestCase):
	def test_item_bom_mapping_keeps_ipd_and_bom_uom(self):
		filtered = filter_doc_fields({
			"doctype": "Item BOM Attribute Mapping",
			"name": "TEST-IBAM-SYNC-CONTRACT",
			"item_production_detail": "TEST-IPD",
			"bom_uom": "Kg",
		})

		self.assertEqual(filtered["item_production_detail"], "TEST-IPD")
		self.assertEqual(filtered["bom_uom"], "Kg")

	def test_item_bom_mapping_upsert_persists_ipd_and_bom_uom(self):
		name = f"_Test IBAM Sync {frappe.generate_hash(length=8)}"
		upsert_doc({
			"doctype": "Item BOM Attribute Mapping",
			"name": name,
			"item_production_detail": "TEST-IPD",
			"bom_uom": "Kg",
		}, event="on_update")

		stored = frappe.get_doc("Item BOM Attribute Mapping", name)
		self.assertEqual(stored.item_production_detail, "TEST-IPD")
		self.assertEqual(stored.bom_uom, "Kg")

	def test_production_order_contract_keeps_business_and_history_fields(self):
		payload = {
			"doctype": "Production Order",
			"name": "TEST-PPO-SYNC-CONTRACT",
			"status": "Open",
			"item": "TEST-ITEM",
			"comment_log": "Created in production_api",
			"ppo_requested_by": "Administrator",
			"ppo_requested_on": "2026-08-17 10:00:00",
			"quantity_ratio_request": "{}",
			"status_change_request": "{}",
			"incoming_quantity_transfer_request": "{}",
			"transferred_to_ppo": "PPO-00002",
			"transferred_on": "2026-08-17 11:00:00",
			"quantity_transfer_history": [{
				"movement": "Reduced",
				"quantity": 5,
				"quantity_before": 20,
				"quantity_after": 15,
			}],
			"date_change_history": [{
				"date_field": "Delivery Date",
				"previous_date": "2026-08-20",
				"new_date": "2026-08-22",
			}],
			"lot_price_overrides": [{
				"lot": "LOT-0001",
				"size": "M",
				"mrp": 499,
			}],
		}
		filtered = filter_doc_fields(payload)

		for fieldname in payload:
			self.assertIn(fieldname, filtered)
		self.assertEqual(filtered["quantity_transfer_history"][0]["quantity_after"], 15)
		self.assertEqual(filtered["date_change_history"][0]["new_date"], "2026-08-22")
		self.assertEqual(filtered["lot_price_overrides"][0]["mrp"], 499)

	def test_production_order_upsert_persists_history_tables(self):
		variant = frappe.get_all(
			"Item Variant",
			fields=["name", "item"],
			filters={"item": ["is", "set"]},
			limit=1,
		)[0]
		name = f"_Test PPO Sync {frappe.generate_hash(length=8)}"
		upsert_doc({
			"doctype": "Production Order",
			"name": name,
			"item": variant.item,
			"status": "Open",
			"comment_log": "Created in production_api",
			"production_order_details": [{
				"item_variant": variant.name,
				"quantity": 20,
				"ratio": 2,
			}],
			"production_ordered_details": [{
				"item_variant": variant.name,
				"lot": "TEST-LOT-0001",
				"quantity": 20,
			}],
			"quantity_transfer_history": [{
				"movement": "Reduced",
				"quantity": 5,
				"quantity_before": 20,
				"quantity_after": 15,
			}],
			"date_change_history": [{
				"date_field": "Delivery Date",
				"previous_date": "2026-08-20",
				"new_date": "2026-08-22",
			}],
			"lot_price_overrides": [{
				"lot": "TEST-LOT-0001",
				"size": "M",
				"mrp": 499,
			}],
		}, event="on_update")

		stored = frappe.get_doc("Production Order", name)
		self.assertEqual(stored.item, variant.item)
		self.assertEqual(stored.status, "Open")
		self.assertEqual(stored.comment_log, "Created in production_api")
		self.assertEqual(stored.production_ordered_details[0].lot, "TEST-LOT-0001")
		self.assertEqual(stored.quantity_transfer_history[0].quantity_after, 15)
		self.assertEqual(stored.date_change_history[0].new_date.isoformat(), "2026-08-22")
		self.assertEqual(stored.lot_price_overrides[0].mrp, 499)

	def test_production_ordered_row_keeps_direct_and_dynamic_lot_links(self):
		with patch("essdee_yrp.sd_yrp_sync.validate_required_link"):
			rows = map_production_ordered_rows({
				"doctype": "Production Order",
				"name": "TEST-PPO-SYNC-CONTRACT",
				"production_ordered_details": [{
					"item_variant": "TEST-VARIANT",
					"lot": "LOT-0001",
					"quantity": 10,
				}],
			})

		self.assertEqual(rows[0]["reference_doctype"], "Lot")
		self.assertEqual(rows[0]["reference_name"], "LOT-0001")
		self.assertEqual(rows[0]["lot"], "LOT-0001")

	def test_mrp_settings_ignores_unavailable_module_fields(self):
		filtered = filter_doc_fields({
			"doctype": "MRP Settings",
			"name": "MRP Settings",
			"enable_price_validation": 1,
			"purchase_invoice_series_map": [{
				"series": "SRC-.YYYY.-",
				"mapped_series": "DST-.YYYY.-",
			}],
			"production_order_action_roles": [{"role": "System Manager"}],
			"production_order_quantity_approver_role": "System Manager",
			"non_set_box_sticker": "TEST-ZPL-FORMAT",
			"sewing_plan_status_summary": [{"input_type": "Sewing"}],
			"default_major_aql_level": "Level-1.5",
		})

		self.assertEqual(filtered["enable_price_validation"], 1)
		self.assertEqual(filtered["purchase_invoice_series_map"][0]["mapped_series"], "DST-.YYYY.-")
		self.assertEqual(filtered["production_order_action_roles"][0]["role"], "System Manager")
		self.assertEqual(filtered["production_order_quantity_approver_role"], "System Manager")
		self.assertEqual(filtered["non_set_box_sticker"], "TEST-ZPL-FORMAT")
		self.assertNotIn("sewing_plan_status_summary", filtered)
		self.assertNotIn("default_major_aql_level", filtered)

	def test_mrp_settings_upsert_replaces_supported_child_tables(self):
		upsert_doc({
			"doctype": "MRP Settings",
			"name": "MRP Settings",
			"production_order_quantity_approver_role": "System Manager",
			"non_set_box_sticker": "TEST-ZPL-FORMAT",
			"purchase_invoice_series_map": [
				{"series": "SRC-.YYYY.-", "mapped_series": "DST-.YYYY.-"},
				{"series": "SRC-2-.YYYY.-", "mapped_series": "DST-2-.YYYY.-"},
			],
			"production_order_action_roles": [{"role": "System Manager"}],
		}, event="on_update")

		settings = frappe.get_single("MRP Settings")
		self.assertEqual(settings.production_order_quantity_approver_role, "System Manager")
		self.assertEqual(settings.non_set_box_sticker, "TEST-ZPL-FORMAT")
		self.assertEqual(
			[(row.series, row.mapped_series) for row in settings.purchase_invoice_series_map],
			[
				("SRC-.YYYY.-", "DST-.YYYY.-"),
				("SRC-2-.YYYY.-", "DST-2-.YYYY.-"),
			],
		)
		self.assertEqual(
			[row.role for row in settings.production_order_action_roles],
			["System Manager"],
		)

	def test_ipd_panel_wise_cloth_mapping_is_syncable(self):
		field = frappe.get_meta("Item Production Detail").get_field("panel_wise_cloth_mapping_json")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "JSON")
		self.assertTrue(field.hidden)

		stored_mapping = frappe.as_json({
			"schema_version": 1,
			"attributes": ["Panel", "Colour"],
			"panels": [{"panel_value": "Front", "values": {"Red": {"cloth": "Dyed Fabric"}}}],
		})
		filtered = filter_doc_fields({
			"doctype": "Item Production Detail",
			"name": "TEST-IPD-PANEL-WISE-CLOTH-MAPPING",
			"panel_wise_cloth_mapping_json": stored_mapping,
		})

		self.assertEqual(filtered["panel_wise_cloth_mapping_json"], stored_mapping)

	def test_lot_cloth_excess_percentage_is_syncable(self):
		field = frappe.get_meta("Lot").get_field("cloth_excess_percentage")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Percent")
		self.assertEqual(field.label, "Cloth Excess Percentage")
		addition_field = frappe.get_meta("Lot").get_field("cloth_program_additions")
		self.assertIsNotNone(addition_field)
		self.assertEqual(addition_field.fieldtype, "JSON")
		stored_additions = frappe.as_json({
			"version": 1,
			"totals": [{"cloth_item": "CLOTH-1", "additional_weight": 20}],
			"routes": [],
		})

		filtered = filter_doc_fields({
			"doctype": "Lot",
			"name": "TEST-LOT-CLOTH-EXCESS",
			"cloth_excess_percentage": 7.5,
			"cloth_program_additions": stored_additions,
		})
		self.assertEqual(filtered["cloth_excess_percentage"], 7.5)
		self.assertEqual(filtered["cloth_program_additions"], stored_additions)

	def test_ipd_compacting_sync_replaces_compacting_child_rows(self):
		self.assertIn("IPD Compacting", SYNC_DOCTYPES)
		name = f"_Test IPD Compacting {frappe.generate_hash(length=8)}"
		base_payload = {
			"doctype": "IPD Compacting",
			"name": name,
			"item_production_detail": name,
			"packing_attribute": "Colour",
			"compacting_details": [
				{
					"cloth_item": "_Test Cloth A",
					"packing_attribute_value": "Red",
					"input_dia": "22 Dia",
					"compacting_dia": "21 Dia",
				},
				{
					"cloth_item": "_Test Cloth B",
					"packing_attribute_value": "Red",
					"input_dia": "22 Dia",
					"compacting_dia": "20 Dia",
				},
			],
		}

		upsert_doc(base_payload, event="after_insert")
		inserted = frappe.get_doc("IPD Compacting", name)
		self.assertEqual(len(inserted.compacting_details), 2)
		self.assertEqual(inserted.compacting_details[0].compacting_dia, "21 Dia")

		updated_payload = dict(base_payload)
		updated_payload["compacting_details"] = [
			{
				"cloth_item": "_Test Cloth A",
				"packing_attribute_value": "Red",
				"input_dia": "22 Dia",
				"compacting_dia": "20 Dia",
			}
		]
		upsert_doc(updated_payload, event="on_update")

		updated = frappe.get_doc("IPD Compacting", name)
		self.assertEqual(len(updated.compacting_details), 1)
		self.assertEqual(updated.compacting_details[0].cloth_item, "_Test Cloth A")
		self.assertEqual(updated.compacting_details[0].compacting_dia, "20 Dia")

	def test_legacy_ipd_consumption_message_targets_ipd_compacting(self):
		name = f"_Test Legacy IPD Compacting {frappe.generate_hash(length=8)}"
		handle_sd_yrp_message({
			"Header": {
				"Topic": "sd_yrp_master",
				"DocType": "IPD Consumption",
				"Event": "on_update",
			},
			"Payload": {
				"doctype": "IPD Consumption",
				"name": name,
				"item_production_detail": name,
				"packing_attribute": "Colour",
				"compacting_details": [{
					"cloth_item": "_Test Cloth A",
					"packing_attribute_value": "Black",
					"input_dia": "24 Dia",
					"compacting_dia": "23 Dia",
				}],
			},
		})

		doc = frappe.get_doc("IPD Compacting", name)
		self.assertEqual(doc.item_production_detail, name)
		self.assertEqual(doc.compacting_details[0].compacting_dia, "23 Dia")

	def test_essdee_production_order_settings_are_self_healing_and_idempotent(self):
		settings = frappe.get_doc({
			"doctype": "YRP Settings",
			"production_order_attributes": [
				{"attribute": "Colour", "is_grid_attribute": 0},
			],
			"po_dependent_attribute": None,
			"po_dependent_attribute_value": None,
		})

		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe, "get_doc", return_value=settings),
			patch.object(settings, "save") as save,
		):
			self.assertTrue(ensure_yrp_production_order_settings())
			grid_rows = [
				row
				for row in settings.production_order_attributes
				if row.attribute == PRODUCTION_ORDER_GRID_ATTRIBUTE
			]
			self.assertEqual(len(grid_rows), 1)
			self.assertEqual(grid_rows[0].is_grid_attribute, 1)
			self.assertEqual(
				[row.attribute for row in settings.production_order_attributes],
				["Colour", PRODUCTION_ORDER_GRID_ATTRIBUTE],
			)
			self.assertEqual(
				settings.po_dependent_attribute,
				PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE,
			)
			self.assertEqual(
				settings.po_dependent_attribute_value,
				PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE,
			)

			self.assertFalse(ensure_yrp_production_order_settings())
			save.assert_called_once_with(ignore_permissions=True)
