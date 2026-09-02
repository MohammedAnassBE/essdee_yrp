from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp import hooks
from essdee_yrp.item_bom_attribute_mapping import (
	_build_mapping_rows,
	get_item_bom_mapping_combinations,
)


class TestItemBOMAttributeMappingCustomization(FrappeTestCase):
	def test_exact_ipd_combinations_are_preserved(self):
		data = {
			"items": [
				{"Colour": "Mint", "Size": "45 cm"},
				{"Colour": "Mint", "Size": "50 cm"},
				{"Colour": "Navy", "Size": "45 cm"},
			]
		}

		rows = _build_mapping_rows(data, ["Colour", "Size"], ["Colour"])

		self.assertEqual(
			rows,
			[
				{
					"item_Colour": "Mint",
					"item_Size": "45 cm",
					"bom_Colour": None,
					"quantity": 0,
					"included": True,
				},
				{
					"item_Colour": "Mint",
					"item_Size": "50 cm",
					"bom_Colour": None,
					"quantity": 0,
					"included": True,
				},
				{
					"item_Colour": "Navy",
					"item_Size": "45 cm",
					"bom_Colour": None,
					"quantity": 0,
					"included": True,
				},
			],
		)

	def test_endpoint_uses_cutting_combinations_from_linked_ipd(self):
		ipd = MagicMock()
		ipd.name = "TEST-IPD-1"
		ipd.item = "TEST-ITEM"
		combination_data = {
			"attributes": ["Colour", "Size"],
			"items": [{"Colour": "Navy", "Size": "45 cm"}],
		}

		with (
			patch.object(frappe, "get_doc", return_value=ipd),
			patch(
				"essdee_yrp.item_bom_attribute_mapping.ipd_ui.get_combination",
				return_value=combination_data,
			) as get_combination,
		):
			rows = get_item_bom_mapping_combinations(
				ipd="TEST-IPD-1",
				item="TEST-ITEM",
				item_attributes='["Colour", "Size"]',
				bom_attributes='["Colour"]',
			)

		ipd.check_permission.assert_called_once_with("read")
		get_combination.assert_called_once_with(
			"TEST-IPD-1", ["Colour", "Size"], "Cutting"
		)
		self.assertEqual(rows[0]["item_Colour"], "Navy")
		self.assertEqual(rows[0]["item_Size"], "45 cm")

	def test_blank_or_duplicate_ipd_rows_do_not_create_broken_grid_rows(self):
		data = {
			"items": [
				{"Colour": "Navy", "Size": "45 cm"},
				{"Colour": "Navy", "Size": "45 cm"},
				{"Colour": None, "Size": "50 cm"},
			]
		}

		rows = _build_mapping_rows(data, ["Colour", "Size"], ["Colour"])

		self.assertEqual(len(rows), 1)

	def test_desk_adapter_is_registered_in_essdee_only(self):
		self.assertEqual(
			hooks.doctype_js['YRP Item BOM Attribute Mapping'],
			"public/js/item_bom_attribute_mapping.js",
		)
		source = (
			Path(frappe.get_app_path("essdee_yrp"))
			/ "public/js/item_bom_attribute_mapping.js"
		).read_text(encoding="utf-8")
		self.assertIn("get_item_bom_mapping_combinations", source)
		self.assertIn("frm.doc.item_production_detail", source)
		self.assertIn("component.toggle_row", source)
		self.assertIn("if (!included)", source)
