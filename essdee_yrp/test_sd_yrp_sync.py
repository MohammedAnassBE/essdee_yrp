import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.sd_yrp_sync import (
	CONSUMER_DOCTYPES,
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
from yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note import (
	get_rework_output_received_types,
)


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
			fields = {(row.get("dt"), row.get("fieldname")): row for row in json.load(fixture_file)}

		self.assertEqual(fields[("Address", "gstin")]["module"], "Essdee YRP")
		self.assertEqual(
			fields[("User", "telegram_user_id")]["module"],
			"Essdee YRP",
		)

	def test_lot_time_and_action_rows_are_syncable(self):
		filtered = filter_doc_fields(
			{
				"doctype": "SD YRP Lot",
				"name": "TEST-LOT-TNA",
				"lot_time_and_action_details": [
					{
						"colour": "Black",
						"master": "Master-00001",
						"time_and_action": "TNA-00001",
					}
				],
			}
		)

		self.assertEqual(
			filtered["lot_time_and_action_details"][0],
			{
				"doctype": "SD YRP Lot Time and Action Detail",
				"colour": "Black",
				"master": "Master-00001",
				"time_and_action": "TNA-00001",
			},
		)

	def test_production_ordered_row_keeps_direct_and_dynamic_lot_links(self):
		with patch("essdee_yrp.sd_yrp_sync.validate_required_link"):
			rows = map_production_ordered_rows(
				{
					"doctype": "YRP Production Order",
					"name": "PPO-TEST",
					"production_ordered_details": [
						{
							"item_variant": "ITEM-S",
							"lot": "LOT-0001",
							"quantity": 12,
						}
					],
				}
			)

		self.assertEqual(
			rows[0],
			{
				"doctype": "YRP Production Ordered Detail",
				"reference_doctype": "SD YRP Lot",
				"reference_name": "LOT-0001",
				"lot": "LOT-0001",
				"item_variant": "ITEM-S",
				"quantity": 12,
			},
		)

	def test_single_sync_replaces_child_table_rows(self):
		upsert_doc(
			{
				"doctype": "SD YRP MRP Settings",
				"name": "SD YRP MRP Settings",
				"enable_price_validation": 1,
				"purchase_invoice_series_map": [
					{"series": "SRC-.YYYY.-", "mapped_series": "DST-.YYYY.-"},
					{"series": "SRC-2-.YYYY.-", "mapped_series": "DST-2-.YYYY.-"},
				],
			},
			event="on_update",
		)

		settings = frappe.get_single("SD YRP MRP Settings")
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
		upsert_doc(
			{
				"doctype": "Supplier",
				"name": name,
				"supplier_name": name,
				"supplier_users": [{"user": "Administrator"}],
			},
			event="after_insert",
		)

		supplier = frappe.get_doc("Supplier", name)
		warehouse = frappe.get_doc("Warehouse", name)
		self.assertEqual([row.user for row in supplier.supplier_users], ["Administrator"])
		self.assertEqual([row.user for row in warehouse.warehouse_users], ["Administrator"])

	def test_lot_cloth_excess_percentage_is_syncable(self):
		field = frappe.get_meta("SD YRP Lot").get_field("cloth_excess_percentage")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Percent")
		self.assertEqual(field.label, "Cloth Excess Percentage")
		addition_field = frappe.get_meta("SD YRP Lot").get_field("cloth_program_additions")
		self.assertIsNotNone(addition_field)
		self.assertEqual(addition_field.fieldtype, "JSON")
		stored_additions = frappe.as_json(
			{
				"version": 1,
				"totals": [{"cloth_item": "CLOTH-1", "additional_weight": 20}],
				"routes": [],
			}
		)

		filtered = filter_doc_fields(
			{
				"doctype": "SD YRP Lot",
				"name": "TEST-LOT-CLOTH-EXCESS",
				"cloth_excess_percentage": 7.5,
				"cloth_program_additions": stored_additions,
			}
		)
		self.assertEqual(filtered["cloth_excess_percentage"], 7.5)
		self.assertEqual(filtered["cloth_program_additions"], stored_additions)

	def test_ipd_compacting_sync_replaces_compacting_child_rows(self):
		self.assertIn("IPD Compacting", SYNC_DOCTYPES)
		name = f"_Test IPD Compacting {frappe.generate_hash(length=8)}"
		base_payload = {
			"doctype": "SD YRP IPD Compacting",
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
		inserted = frappe.get_doc("SD YRP IPD Compacting", name)
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

		updated = frappe.get_doc("SD YRP IPD Compacting", name)
		self.assertEqual(len(updated.compacting_details), 1)
		self.assertEqual(updated.compacting_details[0].cloth_item, "_Test Cloth A")
		self.assertEqual(updated.compacting_details[0].compacting_dia, "20 Dia")

	def test_legacy_ipd_consumption_message_targets_ipd_compacting(self):
		name = f"_Test Legacy IPD Compacting {frappe.generate_hash(length=8)}"
		handle_sd_yrp_message(
			{
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
					"compacting_details": [
						{
							"cloth_item": "_Test Cloth A",
							"packing_attribute_value": "Black",
							"input_dia": "24 Dia",
							"compacting_dia": "23 Dia",
						}
					],
				},
			}
		)

		doc = frappe.get_doc("SD YRP IPD Compacting", name)
		self.assertEqual(doc.item_production_detail, name)
		self.assertEqual(doc.compacting_details[0].compacting_dia, "23 Dia")

	def test_source_and_target_headers_both_resolve_to_target_doctype(self):
		for header_doctype in ("Lot", "SD YRP Lot"):
			with self.subTest(header_doctype=header_doctype):
				with patch("essdee_yrp.sd_yrp_sync.upsert_doc") as upsert:
					handle_sd_yrp_message(
						{
							"Header": {
								"Topic": "sd_yrp_master",
								"DocType": header_doctype,
								"Event": "on_update",
							},
							"Payload": {"doctype": header_doctype, "name": "LOT-TEST"},
						}
					)

				upsert.assert_called_once_with(
					{
						"doctype": "SD YRP Lot",
						"name": "LOT-TEST",
						"_sd_yrp_source_doctype": "Lot",
					},
					event="on_update",
				)

	def test_essdee_production_order_settings_are_self_healing_and_idempotent(self):
		settings = frappe.get_doc(
			{
				"doctype": "YRP Settings",
				"production_order_attributes": [
					{"attribute": "Colour", "is_grid_attribute": 0},
				],
				"po_dependent_attribute": None,
				"po_dependent_attribute_value": None,
			}
		)

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

	def test_configured_production_order_settings_are_never_overwritten(self):
		settings = frappe.get_doc(
			{
				"doctype": "YRP Settings",
				"production_order_attributes": [
					{"attribute": "Colour", "is_grid_attribute": 1},
					{"attribute": PRODUCTION_ORDER_GRID_ATTRIBUTE, "is_grid_attribute": 0},
				],
				"po_dependent_attribute": "Colour",
				"po_dependent_attribute_value": "Red",
			}
		)

		with (
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe, "get_doc", return_value=settings),
			patch.object(settings, "save") as save,
		):
			self.assertFalse(ensure_yrp_production_order_settings())

		save.assert_not_called()
		self.assertEqual(
			[(row.attribute, row.is_grid_attribute) for row in settings.production_order_attributes],
			[("Colour", 1), (PRODUCTION_ORDER_GRID_ATTRIBUTE, 0)],
		)
		self.assertEqual(settings.po_dependent_attribute, "Colour")
		self.assertEqual(settings.po_dependent_attribute_value, "Red")

	def test_grn_received_type_options_include_essdee_classifications(self):
		options = get_rework_output_received_types()["received_types"]

		self.assertTrue({
			"Accepted",
			"Adas",
			"Fabric Mistake",
			"Fusing Mistake",
			"Misstitch",
			"Oil Mark",
			"Other Mistake",
			"Printing Mistake",
			"Rejected",
			"Shade Mistake",
		}.issubset(options))


	def test_grn_item_type_message_creates_received_type(self):
		name = f"_Test Received Type {frappe.generate_hash(length=8)}"
		self.assertIn("GRN Item Type", CONSUMER_DOCTYPES)
		self.assertNotIn("Received Type", CONSUMER_DOCTYPES)
		self.assertIn("YRP Received Type", CONSUMER_DOCTYPES)

		handle_sd_yrp_message({
			"Header": {
				"Topic": "sd_yrp_master",
				"DocType": "GRN Item Type",
				"Event": "on_update",
			},
			"Payload": {
				"doctype": "GRN Item Type",
				"name": name,
				"grn_type": name,
				"type": "Accepted",
			},
		})

		received_type = frappe.get_doc("YRP Received Type", name)
		self.assertEqual(received_type.received_type_name, name)


	def test_item_bom_mapping_keeps_ipd_and_bom_uom(self):
		filtered = filter_doc_fields({
			"doctype": "YRP Item BOM Attribute Mapping",
			"name": "TEST-IBAM-SYNC-CONTRACT",
			"item_production_detail": "TEST-IPD",
			"bom_uom": "Kg",
		})

		self.assertEqual(filtered["item_production_detail"], "TEST-IPD")
		self.assertEqual(filtered["bom_uom"], "Kg")


	def test_item_bom_mapping_upsert_persists_ipd_and_bom_uom(self):
		name = f"_Test IBAM Sync {frappe.generate_hash(length=8)}"
		upsert_doc({
			"doctype": "YRP Item BOM Attribute Mapping",
			"name": name,
			"item_production_detail": "TEST-IPD",
			"bom_uom": "Kg",
		}, event="on_update")

		stored = frappe.get_doc("YRP Item BOM Attribute Mapping", name)
		self.assertEqual(stored.item_production_detail, "TEST-IPD")
		self.assertEqual(stored.bom_uom, "Kg")


	def test_production_order_contract_keeps_business_and_history_fields(self):
		payload = {
			"doctype": "YRP Production Order",
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


	def test_mrp_settings_keeps_supported_module_fields(self):
		filtered = filter_doc_fields({
			"doctype": "SD YRP MRP Settings",
			"name": "SD YRP MRP Settings",
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
		self.assertEqual(filtered["sewing_plan_status_summary"][0]["input_type"], "Sewing")
		self.assertEqual(filtered["default_major_aql_level"], "Level-1.5")


	def test_mrp_settings_upsert_replaces_supported_child_tables(self):
		upsert_doc({
			"doctype": "SD YRP MRP Settings",
			"name": "SD YRP MRP Settings",
			"production_order_quantity_approver_role": "System Manager",
			"non_set_box_sticker": "TEST-ZPL-FORMAT",
			"purchase_invoice_series_map": [
				{"series": "SRC-.YYYY.-", "mapped_series": "DST-.YYYY.-"},
				{"series": "SRC-2-.YYYY.-", "mapped_series": "DST-2-.YYYY.-"},
			],
			"production_order_action_roles": [{"role": "System Manager"}],
		}, event="on_update")

		settings = frappe.get_single("SD YRP MRP Settings")
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
		field = frappe.get_meta("YRP Item Production Detail").get_field("panel_wise_cloth_mapping_json")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "JSON")
		self.assertTrue(field.hidden)

		stored_mapping = frappe.as_json({
			"schema_version": 1,
			"attributes": ["Panel", "Colour"],
			"panels": [{"panel_value": "Front", "values": {"Red": {"cloth": "Dyed Fabric"}}}],
		})
		filtered = filter_doc_fields({
			"doctype": "YRP Item Production Detail",
			"name": "TEST-IPD-PANEL-WISE-CLOTH-MAPPING",
			"panel_wise_cloth_mapping_json": stored_mapping,
		})

		self.assertEqual(filtered["panel_wise_cloth_mapping_json"], stored_mapping)
