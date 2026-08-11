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
	upsert_doc,
)
from essdee_yrp.setup import ensure_yrp_production_order_settings


class TestSDYRPSyncSetup(IntegrationTestCase):
	def test_lot_cloth_excess_percentage_is_syncable(self):
		field = frappe.get_meta("Lot").get_field("cloth_excess_percentage")
		self.assertIsNotNone(field)
		self.assertEqual(field.fieldtype, "Percent")
		self.assertEqual(field.label, "Cloth Excess Percentage")

		filtered = filter_doc_fields({
			"doctype": "Lot",
			"name": "TEST-LOT-CLOTH-EXCESS",
			"cloth_excess_percentage": 7.5,
		})
		self.assertEqual(filtered["cloth_excess_percentage"], 7.5)

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
