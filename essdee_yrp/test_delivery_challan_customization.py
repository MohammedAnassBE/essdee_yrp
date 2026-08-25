from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.cutting.movement import (
	_overlay_source_rows,
)
from essdee_yrp.delivery_challan_hooks import before_validate
from essdee_yrp.item_matrix import normalize_item_matrix_row_indexes


class TestDeliveryChallanCustomization(FrappeTestCase):
	def test_production_api_fields_are_essdee_custom_fields(self):
		meta = frappe.get_meta("Delivery Challan", cached=False)
		expected = {
			"actual_date": ("Date", None),
			"additional_goods_value": ("Currency", None),
			"allow_non_bundle": ("Check", None),
			"cut_panel_movement": ("Link", "Cut Panel Movement"),
			"from_address": ("Link", "Address"),
			"from_address_details": ("Small Text", None),
			"from_finishing": ("Check", None),
			"from_location_name": ("Data", None),
			"includes_packing": ("Check", None),
			"letter_head": ("Link", "Letter Head"),
			"loose_piece_dc": ("Check", None),
			"pack_piece_dc": ("Check", None),
			"supplier_address": ("Link", "Address"),
			"supplier_address_details": ("Small Text", None),
			"supplier_name": ("Data", None),
		}

		for fieldname, definition in expected.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				self.assertEqual((field.fieldtype, field.options), definition)
				self.assertTrue(
					frappe.db.exists(
						"Custom Field",
						{
							"dt": "Delivery Challan",
							"fieldname": fieldname,
							"module": "Essdee YRP",
						},
					)
				)

	def test_approved_field_attributes(self):
		meta = frappe.get_meta("Delivery Challan", cached=False)

		self.assertEqual(meta.get_field("from_location").reqd, 1)
		self.assertEqual(meta.get_field("is_internal_unit").read_only, 1)
		self.assertFalse(meta.get_field("is_internal_unit").fetch_from)
		self.assertEqual(meta.get_field("is_rework").read_only, 1)
		self.assertEqual(meta.get_field("is_rework").fetch_from, "work_order.is_rework")

		lot = meta.get_field("lot")
		self.assertEqual(
			(lot.reqd, lot.read_only, lot.fetch_from, lot.fetch_if_empty),
			(1, 1, "work_order.lot", 1),
		)

		ste_transferred = meta.get_field("ste_transferred")
		self.assertEqual(ste_transferred.depends_on, "eval: doc.is_internal_unit")
		self.assertEqual(str(ste_transferred.precision), "2")
		self.assertEqual(
			meta.get_field("transfer_complete").depends_on,
			"eval: doc.is_internal_unit",
		)
		self.assertEqual(meta.get_field("vehicle_no").allow_on_submit, 1)

	def test_better_base_attributes_are_preserved(self):
		parent = frappe.get_meta("Delivery Challan", cached=False)
		child = frappe.get_meta("Delivery Challan Item", cached=False)

		self.assertEqual(parent.get_field("naming_series").options, "DC-.YYYY.-")
		self.assertEqual(parent.get_field("comments").fieldtype, "Small Text")
		self.assertEqual(parent.get_field("supplier").fetch_from, "to_warehouse.supplier")
		self.assertEqual(str(parent.get_field("total_delivered_qty").precision), "3")
		self.assertEqual(str(child.get_field("pending_quantity").precision), "3")
		self.assertEqual(str(child.get_field("secondary_qty").precision), "3")

	def test_work_order_context_is_enforced_server_side(self):
		doc = frappe.new_doc("Delivery Challan")
		doc.work_order = "TEST-WO"
		doc.is_internal_unit = 0

		with patch(
			"essdee_yrp.delivery_challan_hooks.frappe.db.get_value",
			return_value=frappe._dict(
				is_internal_unit=1,
				is_rework=1,
				lot="LOT-001",
				includes_packing=1,
			),
		):
			before_validate(doc)

		# Transaction routing is computed by base Delivery Challan from both
		# endpoints; the Work Order's supplier-only flag must not overwrite it.
		self.assertEqual(doc.is_internal_unit, 0)
		self.assertEqual(doc.is_rework, 1)
		self.assertEqual(doc.lot, "LOT-001")
		self.assertEqual(doc.includes_packing, 1)

	def test_cutting_dc_sizes_share_one_logical_row(self):
		variants = {
			"BOTTOM-LEFT-45": frappe._dict(
				item="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Stage", attribute_value="Cut"),
					frappe._dict(attribute="Panel", attribute_value="Bottom Front Left"),
					frappe._dict(attribute="Colour", attribute_value="Dark Grey"),
					frappe._dict(attribute="Size", attribute_value="45 cm"),
				],
			),
			"BOTTOM-LEFT-50": frappe._dict(
				item="Maze Capri Set R.N.S",
				attributes=[
					frappe._dict(attribute="Stage", attribute_value="Cut"),
					frappe._dict(attribute="Panel", attribute_value="Bottom Front Left"),
					frappe._dict(attribute="Colour", attribute_value="Dark Grey"),
					frappe._dict(attribute="Size", attribute_value="50 cm"),
				],
			),
		}
		item = frappe._dict(primary_attribute="Size")

		def get_cached_doc(doctype, name):
			return variants[name] if doctype == "Item Variant" else item

		rows = [
			frappe._dict(
				item_variant=variant,
				lot="C0826-57",
				received_type="Accepted",
				set_combination={"major_part": "Bottom", "major_colour": "Dark Grey"},
			)
			for variant in variants
		]
		with (
			patch(
				"essdee_yrp.item_matrix.frappe.get_cached_doc",
				side_effect=get_cached_doc,
			),
			patch(
				"essdee_yrp.item_matrix.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
		):
			normalized = normalize_item_matrix_row_indexes(rows)

		self.assertEqual(len({row.row_index for row in normalized}), 1)

	def test_cpm_display_indexes_replace_work_order_indexes(self):
		source_rows = [
			{
				"item_variant": variant,
				"qty": 10,
				"row_index": source_index,
				"table_index": source_index,
				"conversion_factor": 1,
				"set_combination": {},
			}
			for variant, source_index in (("BOTTOM-LEFT-45", 11), ("BOTTOM-LEFT-50", 12))
		]
		movement_rows = [
			frappe._dict(
				item_variant=variant,
				qty=qty,
				row_index=3,
				table_index=2,
				set_combination={},
			)
			for variant, qty in (("BOTTOM-LEFT-45", 12), ("BOTTOM-LEFT-50", 18))
		]

		overlaid = _overlay_source_rows(
			source_rows,
			movement_rows,
			target_doctype="Delivery Challan",
		)

		self.assertEqual([row.qty for row in overlaid], [12, 18])
		self.assertEqual({row.row_index for row in overlaid}, {3})
		self.assertEqual({row.table_index for row in overlaid}, {2})
