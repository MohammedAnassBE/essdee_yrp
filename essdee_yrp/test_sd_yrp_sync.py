import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.sd_yrp_sync import (
	PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE,
	PRODUCTION_ORDER_DEPENDENT_ATTRIBUTE_VALUE,
	PRODUCTION_ORDER_GRID_ATTRIBUTE,
	SYNC_DOCTYPES,
	ensure_consumer_config,
	filter_doc_fields,
	handle_sd_yrp_message,
	map_production_ordered_rows,
	upsert_doc,
)
from essdee_yrp.setup import ensure_yrp_production_order_settings


class TestSDYRPSyncSetup(IntegrationTestCase):
	def test_consumer_setup_is_a_noop_when_optional_spine_is_not_installed(self):
		with (
			patch.object(
				frappe,
				"get_installed_apps",
				return_value=["frappe", "yrp", "essdee_yrp"],
			),
			patch.object(frappe, "get_all") as get_all,
		):
			self.assertFalse(ensure_consumer_config())

		get_all.assert_not_called()

	def test_business_identity_fields_are_packaged_in_essdee_fixture(self):
		with open(
			frappe.get_app_path("essdee_yrp", "fixtures", "custom_field.json"),
			encoding="utf-8",
		) as fixture_file:
			fields = {
				(row.get("dt"), row.get("fieldname")): row
				for row in json.load(fixture_file)
			}

		self.assertEqual(fields[("Address", "gstin")]["module"], "Essdee YRP")
		self.assertEqual(
			fields[("User", "telegram_user_id")]["module"],
			"Essdee YRP",
		)

	def test_lot_time_and_action_rows_are_syncable(self):
		filtered = filter_doc_fields({
			"doctype": 'SD YRP Lot',
			"name": "TEST-LOT-TNA",
			"lot_time_and_action_details": [{
				"colour": "Black",
				"master": "Master-00001",
				"time_and_action": "TNA-00001",
			}],
		})

		self.assertEqual(
			filtered["lot_time_and_action_details"][0],
			{
				"doctype": 'SD YRP Lot Time and Action Detail',
				"colour": "Black",
				"master": "Master-00001",
				"time_and_action": "TNA-00001",
			},
		)

	def test_production_ordered_row_keeps_direct_and_dynamic_lot_links(self):
		with patch("essdee_yrp.sd_yrp_sync.validate_required_link"):
			rows = map_production_ordered_rows({
				"doctype": 'YRP Production Order',
				"name": "PPO-TEST",
				"production_ordered_details": [{
					"item_variant": "ITEM-S",
					"lot": "LOT-0001",
					"quantity": 12,
				}],
			})

		self.assertEqual(
			rows[0],
			{
				"doctype": 'YRP Production Ordered Detail',
				"reference_doctype": 'SD YRP Lot',
				"reference_name": "LOT-0001",
				"lot": "LOT-0001",
				"item_variant": "ITEM-S",
				"quantity": 12,
			},
		)

	def test_single_sync_replaces_child_table_rows(self):
		upsert_doc({
			"doctype": 'SD YRP MRP Settings',
			"name": 'SD YRP MRP Settings',
			"enable_price_validation": 1,
			"purchase_invoice_series_map": [
				{"series": "SRC-.YYYY.-", "mapped_series": "DST-.YYYY.-"},
				{"series": "SRC-2-.YYYY.-", "mapped_series": "DST-2-.YYYY.-"},
			],
		}, event="on_update")

		settings = frappe.get_single('SD YRP MRP Settings')
		self.assertEqual(settings.enable_price_validation, 1)
		self.assertEqual(
			[(row.series, row.mapped_series) for row in settings.purchase_invoice_series_map],
			[
				("SRC-.YYYY.-", "DST-.YYYY.-"),
				("SRC-2-.YYYY.-", "DST-2-.YYYY.-"),
			],
		)

	def test_supplier_users_remain_on_supplier_and_map_to_warehouse(self):
		name = f"_Test Sync Supplier {frappe.generate_hash(length=8)}"
		upsert_doc({
			"doctype": 'YRP Supplier',
			"name": name,
			"supplier_name": name,
			"supplier_users": [{"user": "Administrator"}],
		}, event="after_insert")

		supplier = frappe.get_doc('YRP Supplier', name)
		warehouse = frappe.get_doc('YRP Warehouse', name)
		self.assertEqual([row.user for row in supplier.supplier_users], ["Administrator"])
		self.assertEqual([row.user for row in warehouse.warehouse_users], ["Administrator"])

	def test_lot_cloth_excess_percentage_is_syncable(self):
		field = frappe.get_meta('SD YRP Lot').get_field("cloth_excess_percentage")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Percent")
		self.assertEqual(field.label, "Cloth Excess Percentage")
		addition_field = frappe.get_meta('SD YRP Lot').get_field("cloth_program_additions")
		self.assertIsNotNone(addition_field)
		self.assertEqual(addition_field.fieldtype, "JSON")
		stored_additions = frappe.as_json({
			"version": 1,
			"totals": [{"cloth_item": "CLOTH-1", "additional_weight": 20}],
			"routes": [],
		})

		filtered = filter_doc_fields({
			"doctype": 'SD YRP Lot',
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
			"doctype": 'SD YRP IPD Compacting',
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
		inserted = frappe.get_doc('SD YRP IPD Compacting', name)
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

		updated = frappe.get_doc('SD YRP IPD Compacting', name)
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

		doc = frappe.get_doc('SD YRP IPD Compacting', name)
		self.assertEqual(doc.item_production_detail, name)
		self.assertEqual(doc.compacting_details[0].compacting_dia, "23 Dia")

	def test_source_and_target_headers_both_resolve_to_target_doctype(self):
		for header_doctype in ("Lot", "SD YRP Lot"):
			with self.subTest(header_doctype=header_doctype):
				with patch("essdee_yrp.sd_yrp_sync.upsert_doc") as upsert:
					handle_sd_yrp_message({
						"Header": {
							"Topic": "sd_yrp_master",
							"DocType": header_doctype,
							"Event": "on_update",
						},
						"Payload": {"doctype": header_doctype, "name": "LOT-TEST"},
					})

				upsert.assert_called_once_with(
					{"doctype": "SD YRP Lot", "name": "LOT-TEST"},
					event="on_update",
				)

	def test_essdee_production_order_settings_are_self_healing_and_idempotent(self):
		settings = frappe.get_doc({
			"doctype": 'YRP YRP Settings',
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
