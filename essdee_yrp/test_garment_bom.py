from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.garment_bom import calculate_essdee_accessory_bom


class TestGarmentBOM(FrappeTestCase):
	def test_work_order_calculation_rejects_unmapped_attribute_accessory(self):
		ipd = frappe._dict(
			name="_Test Garment IPD",
			item="_Test Garment",
			item_bom=[
				frappe._dict(
					idx=16,
					item="Tag Bullet",
					process_name="Packing",
					dependent_attribute_value="Piece",
					qty_of_product=1,
					qty_of_bom_item=1,
					uom="Nos",
					based_on_attribute_mapping=0,
					attribute_mapping=None,
					wastage_pct=0,
				)
			],
		)
		lot = frappe._dict(pack_in_stage="Piece", pack_out_stage="Pack")
		garment_variant = frappe._dict(item="_Test Garment", attributes=[])
		accessory_item = frappe._dict(
			attributes=[frappe._dict(attribute="Colour")],
		)

		def get_cached_doc(doctype, name):
			if doctype == 'YRP Item Variant':
				return garment_variant
			if doctype == 'YRP Item' and name == "Tag Bullet":
				return accessory_item
			raise AssertionError((doctype, name))

		with (
			patch.object(frappe, "get_doc", return_value=ipd),
			patch.object(frappe, "get_cached_doc", side_effect=get_cached_doc),
			patch("essdee_yrp.garment_bom.get_or_create_variant") as get_variant,
			self.assertRaisesRegex(
				frappe.ValidationError,
				"Tag Bullet.*Colour.*has no attribute mapping",
			),
		):
			calculate_essdee_accessory_bom(
				ipd.name,
				[{"item_variant": "_Test Garment Variant", "qty": 15}],
				lot,
				process_names=["Packing"],
			)

		get_variant.assert_not_called()

	def test_explicit_empty_process_filter_evaluates_no_bom_rows(self):
		ipd = frappe._dict(
			name="_Test Garment IPD",
			item="_Test Garment",
			item_bom=[
				frappe._dict(
					item="_Test Sticker",
					process_name="Yolk Fusing",
					based_on_attribute_mapping=1,
					attribute_mapping="_Invalid Unrelated Mapping",
					wastage_pct=0,
				)
			],
		)
		lot = frappe._dict(pack_in_stage="Piece", pack_out_stage="Pack")
		variant = frappe._dict(item="_Test Garment", attributes=[])

		with (
			patch.object(frappe, "get_doc", return_value=ipd),
			patch.object(frappe, "get_cached_doc", return_value=variant),
			patch("essdee_yrp.garment_bom.get_or_create_variant") as get_variant,
		):
			rows = calculate_essdee_accessory_bom(
				ipd.name,
				[{"item_variant": "_Test Garment Variant", "qty": 10}],
				lot,
				process_names=[],
			)

		self.assertEqual(rows, [])
		get_variant.assert_not_called()

	def test_process_filter_skips_unrelated_accessory_mappings(self):
		ipd = frappe._dict(
			name="_Test Garment IPD",
			item="_Test Garment",
			item_bom=[
				frappe._dict(
					item="_Test Cloth",
					process_name="Cutting",
					dependent_attribute_value="Piece",
					qty_of_product=1,
					qty_of_bom_item=1,
					uom="Kg",
					based_on_attribute_mapping=0,
					attribute_mapping=None,
					wastage_pct=0,
				),
				frappe._dict(
					item="_Test Sticker",
					process_name="Yolk Fusing",
					based_on_attribute_mapping=1,
					attribute_mapping="_Invalid Unrelated Mapping",
					wastage_pct=0,
				),
			],
		)
		lot = frappe._dict(pack_in_stage="Piece", pack_out_stage="Pack")
		variant = frappe._dict(item="_Test Garment", attributes=[])

		with (
			patch.object(frappe, "get_doc", return_value=ipd),
			patch.object(frappe, "get_cached_doc", return_value=variant),
			patch("essdee_yrp.garment_bom.get_or_create_variant", return_value="_Test Cloth") as get_variant,
		):
			rows = calculate_essdee_accessory_bom(
				ipd.name,
				[{"item_variant": "_Test Garment Variant", "qty": 10}],
				lot,
				process_names=["Cutting"],
			)

		get_variant.assert_called_once_with("_Test Cloth", {})
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["required_qty"], 10)

	def test_pack_out_accessory_uses_packing_combo(self):
		ipd = frappe._dict(
			name="_Test Garment IPD",
			item="_Test Garment",
			packing_combo=5,
			is_set_item=0,
			item_bom=[
				frappe._dict(
					item="_Test Box",
					process_name="Packing",
					dependent_attribute_value="Pack",
					qty_of_product=1,
					qty_of_bom_item=1,
					uom="Nos",
					based_on_attribute_mapping=0,
					attribute_mapping=None,
					wastage_pct=0,
				)
			],
		)
		lot = frappe._dict(
			pack_in_stage="Piece",
			pack_out_stage="Pack",
			packing_uom="Pieces",
		)
		variant = frappe._dict(
			item="_Test Garment",
			attributes=[],
		)
		item = frappe._dict(
			default_unit_of_measure="Pieces",
			uom_conversion_details=[],
		)

		def get_cached_doc(doctype, name):
			return variant if doctype == 'YRP Item Variant' else item

		with (
			patch.object(frappe, "get_doc", return_value=ipd),
			patch.object(frappe, "get_cached_doc", side_effect=get_cached_doc),
			patch("essdee_yrp.garment_bom.get_or_create_variant", return_value="_Test Box"),
		):
			rows = calculate_essdee_accessory_bom(
				ipd.name,
				[{"item_variant": "_Test Garment Variant", "qty": 100}],
				lot,
			)

		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["required_qty"], 20)

	def test_attribute_mapping_uses_explicit_bom_attributes(self):
		ipd = frappe._dict(
			name="_Test Garment IPD",
			item="_Test Garment",
			packing_combo=5,
			is_set_item=0,
			item_bom=[
				frappe._dict(
					item="_Test Elastic",
					process_name="Stitching",
					dependent_attribute_value="Piece",
					qty_of_product=1,
					qty_of_bom_item=1,
					uom="Meter",
					based_on_attribute_mapping=1,
					attribute_mapping="_Test Mapping",
					wastage_pct=0,
				)
			],
		)
		lot = frappe._dict(
			pack_in_stage="Piece",
			pack_out_stage="Pack",
			packing_uom="Pieces",
		)
		variant = frappe._dict(
			item="_Test Garment",
			attributes=[frappe._dict(attribute="Colour", attribute_value="Navy")],
		)
		mapping = frappe._dict(
			item_attributes=[frappe._dict(attribute="Colour", same_attribute=0)],
			bom_item_attributes=[frappe._dict(attribute="Size", same_attribute=0)],
			values=[
				frappe._dict(
					index=0,
					type="item",
					attribute="Colour",
					attribute_value="Navy",
					quantity=1.05,
				),
				frappe._dict(
					index=0,
					type="bom",
					attribute="Size",
					attribute_value="8 mm",
					quantity=1.05,
				),
			],
		)

		def get_cached_doc(doctype, name):
			return variant if doctype == 'YRP Item Variant' else mapping

		with (
			patch.object(frappe, "get_doc", return_value=ipd),
			patch.object(frappe, "get_cached_doc", side_effect=get_cached_doc),
			patch(
				"essdee_yrp.garment_bom.get_or_create_variant",
				return_value="_Test Elastic-8 mm",
			) as get_variant,
		):
			rows = calculate_essdee_accessory_bom(
				ipd.name,
				[{"item_variant": "_Test Garment Variant", "qty": 10}],
				lot,
			)

		get_variant.assert_called_once_with("_Test Elastic", {"Size": "8 mm"})
		self.assertEqual(rows[0]["required_qty"], 10.5)

	def test_attribute_mapping_rejects_missing_bom_values(self):
		ipd = frappe._dict(
			name="_Test Garment IPD",
			item="_Test Garment",
			item_bom=[
				frappe._dict(
					item="_Test Elastic",
					process_name="Stitching",
					dependent_attribute_value="Piece",
					qty_of_product=1,
					qty_of_bom_item=1,
					uom="Meter",
					based_on_attribute_mapping=1,
					attribute_mapping="_Incomplete Mapping",
					wastage_pct=0,
				)
			],
		)
		lot = frappe._dict(pack_in_stage="Piece", pack_out_stage="Pack")
		variant = frappe._dict(
			item="_Test Garment",
			attributes=[frappe._dict(attribute="Colour", attribute_value="Navy")],
		)
		mapping = frappe._dict(
			item_attributes=[frappe._dict(attribute="Colour", same_attribute=0)],
			bom_item_attributes=[frappe._dict(attribute="Size", same_attribute=0)],
			values=[
				frappe._dict(
					index=0,
					type="item",
					attribute="Colour",
					attribute_value="Navy",
					quantity=1,
				)
			],
		)

		def get_cached_doc(doctype, name):
			return variant if doctype == 'YRP Item Variant' else mapping

		with (
			patch.object(frappe, "get_doc", return_value=ipd),
			patch.object(frappe, "get_cached_doc", side_effect=get_cached_doc),
			self.assertRaisesRegex(frappe.ValidationError, "missing BOM values for: Size"),
		):
			calculate_essdee_accessory_bom(
				ipd.name,
				[{"item_variant": "_Test Garment Variant", "qty": 10}],
				lot,
			)
