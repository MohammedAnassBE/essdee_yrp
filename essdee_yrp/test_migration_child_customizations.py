import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase
from yrp.stock.dimensions import (
	MANAGED_DIMENSION_FIELD_MARKER,
	get_stock_dimensions,
)


class TestMigrationChildCustomizations(FrappeTestCase):
	def test_custom_field_fixture_excludes_cross_app_generated_fields(self):
		fixture_path = Path(frappe.get_app_path("essdee_yrp", "fixtures", "custom_field.json"))
		rows = json.loads(fixture_path.read_text())
		self.assertEqual(len(rows), len({row["name"] for row in rows}))
		for row in rows:
			self.assertNotIn(
				row.get("module"),
				{"YRP", "YRP E-Waybill Integration"},
				row["name"],
			)
			self.assertNotIn(
				MANAGED_DIMENSION_FIELD_MARKER,
				row.get("description") or "",
				row["name"],
			)

	def assert_essdee_fields(self, doctype, expected):
		meta = frappe.get_meta(doctype, cached=False)
		for fieldname, properties in expected.items():
			with self.subTest(doctype=doctype, fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				for property_name, value in properties.items():
					self.assertEqual(field.get(property_name), value)
				self.assertTrue(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": doctype,
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

	def test_item_production_detail_payload_fields(self):
		self.assert_essdee_fields(
			"Item Production Detail",
			{
				"compacting_details_json": {"fieldtype": "JSON", "hidden": 1},
				"panel_wise_cloth_mapping_json": {
					"fieldtype": "JSON",
					"hidden": 1,
				},
			},
		)

	def test_delivery_challan_item_fields(self):
		self.assert_essdee_fields(
			"Delivery Challan Item",
			{
				"additional_goods_value": {"fieldtype": "Currency"},
				"additional_parameters": {"fieldtype": "Data"},
				"is_calculated": {"fieldtype": "Check", "default": "0"},
				"stock_value": {"fieldtype": "Currency"},
			},
		)
		self.assertIsNone(
			frappe.get_meta("Delivery Challan Item", cached=False).get_field("item_type")
		)

	def test_stock_transfer_children_have_every_configured_dimension(self):
		dimensions = get_stock_dimensions()
		self.assertTrue(dimensions)

		for doctype in (
			"Delivery Challan Item",
			"Goods Received Note Item",
			"Stock Entry Detail",
		):
			meta = frappe.get_meta(doctype, cached=False)
			for dimension in dimensions:
				with self.subTest(
					doctype=doctype,
					fieldname=dimension.fieldname,
				):
					field = meta.get_field(dimension.fieldname)
					self.assertIsNotNone(field)
					self.assertEqual(
						(field.fieldtype, field.options, field.description),
						(
							"Link",
							dimension.dimension_doctype,
							MANAGED_DIMENSION_FIELD_MARKER,
						),
					)

	def test_goods_received_note_item_fields(self):
		self.assert_essdee_fields(
			"Goods Received Note Item",
			{
				"received_types": {"fieldtype": "JSON"},
				"rework_quantity": {"fieldtype": "Float"},
				"secondary_qty_json": {"fieldtype": "JSON"},
				"ste_delivered_quantity": {
					"fieldtype": "Float",
					"allow_on_submit": 1,
				},
				"stock_uom_rate": {"fieldtype": "Currency"},
				"tax": {"fieldtype": "Link", "options": "Tax Slab"},
			},
		)

	def test_stock_entry_detail_set_combination(self):
		self.assert_essdee_fields(
			"Stock Entry Detail",
			{"set_combination": {"fieldtype": "JSON"}},
		)
