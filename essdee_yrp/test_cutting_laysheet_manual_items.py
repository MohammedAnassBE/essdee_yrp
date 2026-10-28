import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.cutting.laysheet_manual_items import build_manual_item_details, get_web_manual_items
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet import sd_yrp_cutting_laysheet as controller

SIZES = ["75 cm", "80 cm"]
COLOURS = {"Navy", "Red"}
SET_FIELDS = [
	{"fieldname": "major_panel", "fieldtype": "Data", "default": "Front"},
	{"fieldname": "major_colour", "fieldtype": "Data", "default": "Navy"},
	{"fieldname": "is_same_packing_attribute", "fieldtype": "Check", "hidden": True, "default": 1},
	{"fieldname": "is_set_item", "fieldtype": "Check", "hidden": True, "default": 0},
]


def row(**values):
	return {
		"colour": "Navy",
		"major_colour": "Navy",
		"shade": "A",
		"quantity": 120,
		"multipliers": {"75 cm": 0, "80 cm": 2},
		**values,
	}


def build(rows, is_set_item=0):
	return build_manual_item_details(rows, SIZES, COLOURS, is_set_item, lambda colour: SET_FIELDS)


class TestBuildManualItemDetails(TestCase):
	def test_rows_are_shaped_like_the_desk_grid(self):
		details = build(
			[row(), row(colour="Red", major_colour="Red", quantity="60", multipliers={"75 cm": "1"})]
		)
		self.assertEqual(
			details[0],
			{
				"colour": "Navy",
				"major_colour": "Navy",
				"quantity": 120,
				"shade": "A",
				"manual_index": 0,
				"75 cm": 0,
				"80 cm": 2,
				"major_panel": "Front",
				"is_same_packing_attribute": 1,
				"is_set_item": 0,
			},
		)
		self.assertEqual(details[1]["major_colour"], "Red")
		self.assertEqual((details[1]["quantity"], details[1]["75 cm"], details[1]["80 cm"]), (60, 1, 0))

	def test_saved_rows_match_the_desk_set_combination(self):
		with patch.object(controller, "get_primary_values", return_value=SIZES):
			saved = controller.save_manual_item_details({"manual_items": build([row()])}, "CLS-1")
		self.assertEqual(
			[(item["size"], item["multiplier"], item["quantity"]) for item in saved],
			[("75 cm", 0, 120), ("80 cm", 2, 120)],
		)
		self.assertEqual(
			saved[0]["set_combination"],
			{
				"major_colour": "Navy",
				"major_panel": "Front",
				"is_same_packing_attribute": 1,
				"is_set_item": 0,
			},
		)

	def test_empty_list_clears_every_row(self):
		self.assertEqual(build([]), {})

	def test_desk_validations(self):
		cases = [
			(row(colour=""), "Enter Colour"),
			(row(major_colour=""), "Enter Major Colour"),
			(row(shade=" "), "Enter the Shade"),
			(row(quantity=0), "Quantity should be greater than Zero"),
			(row(quantity=1.5), "whole number"),
			(row(multipliers={"75 cm": -1, "80 cm": 2}), "Negative Multiplier"),
			(row(multipliers={"75 cm": 0, "80 cm": ""}), "atleast one size"),
			(row(multipliers={"90 cm": 1}), "Unknown size 90 cm"),
			(row(colour="Green"), "Colour Green is not available"),
		]
		for value, message in cases:
			with self.subTest(message=message), self.assertRaisesRegex(frappe.ValidationError, message):
				build([value])

	def test_set_item_requires_set_colour(self):
		with self.assertRaisesRegex(frappe.ValidationError, "Bundle Row 1: Enter Set Colour"):
			build([row()], is_set_item=1)
		self.assertEqual(build([row(set_colour="Red")], is_set_item=1)[0]["set_colour"], "Red")

	def test_stored_rows_round_trip_to_the_web_grid(self):
		stored = {
			0: {
				"colour": "Navy",
				"major_colour": "Navy",
				"shade": "A",
				"quantity": 120,
				"manual_index": 0,
				"75 cm": 0,
				"80 cm": 2,
				"major_panel": "Front",
			}
		}
		self.assertEqual(get_web_manual_items(stored, SIZES), [{**row(), "set_colour": ""}])


class TestWebManualItemSave(TestCase):
	def doc(self, is_manual_entry=1):
		return SimpleNamespace(
			name="CLS-1",
			is_manual_entry=is_manual_entry,
			is_set_item=0,
			cutting_marker="CM-1",
			cutting_laysheet_manual_items=[],
		)

	def test_non_manual_laysheet_rejects_bundle_entries(self):
		with self.assertRaisesRegex(frappe.ValidationError, "only on a Manual Entry Cutting LaySheet"):
			controller.get_web_manual_item_details(self.doc(is_manual_entry=0), json.dumps([row()]), "CP-1")

	def test_non_manual_cloth_save_keeps_no_bundle_entries(self):
		self.assertEqual(
			controller.get_web_manual_item_details(self.doc(is_manual_entry=0), None, "CP-1"), {}
		)

	def test_cloth_only_save_keeps_stored_bundle_entries(self):
		with patch.object(
			controller, "fetch_manual_item_details", return_value={0: {"colour": "Navy"}}
		) as fetch:
			self.assertEqual(
				controller.get_web_manual_item_details(self.doc(), None, "CP-1"), {0: {"colour": "Navy"}}
			)
		fetch.assert_called_once()

	def test_posted_rows_use_plan_colours_sizes_and_marker_set_fields(self):
		with (
			patch.object(controller, "get_select_attributes", return_value={"colour": COLOURS}) as attributes,
			patch.object(controller, "get_primary_values", return_value=SIZES),
			patch.object(controller, "get_input_fields", return_value={"input_fields": SET_FIELDS}) as fields,
		):
			details = controller.get_web_manual_item_details(
				self.doc(), json.dumps([row(), row(shade="B")]), "CP-1"
			)
		attributes.assert_called_once_with(cutting_plan="CP-1", cutting_order=None)
		fields.assert_called_once_with("CM-1", "Navy", {"colour": ["Navy", "Red"]})
		self.assertEqual([detail["shade"] for detail in details.values()], ["A", "B"])


class TestManualClothDetails(TestCase):
	def test_web_manual_cloth_row_without_bits_saves_zero_bits(self):
		ipd = SimpleNamespace(
			packing_attribute="Colour", cloth_detail=[SimpleNamespace(name1="Main Fabric", cloth="Cloth")]
		)
		cloth = {
			"cloth_type": "Main Fabric",
			"colour": "Navy",
			"dia": "13 Dia",
			"actual_dia": "13 Dia",
			"shade": "A",
			"weight": 10,
			"balance_weight": 1,
			"used_weight": 9,
			"no_of_rolls": 1,
			"no_of_bits": None,
			"end_bit_weight": None,
			"fabric_type": "Tubler",
			"items_json": {},
			"set_combination": {},
		}
		with (
			patch.object(controller, "get_detail_doc", return_value=ipd),
			patch.object(controller, "get_combined_combination", return_value=({}, False)),
			patch.object(controller, "get_dia_attribute", return_value="Dia"),
			patch.object(controller, "get_or_create_variant", return_value="Cloth-Navy"),
		):
			saved = controller.save_item_details({"cloth_items": [cloth]}, "CP-1", "Front", 1)
		self.assertEqual(
			(saved[0]["no_of_bits"], saved[0]["effective_bits"], saved[0]["end_bit_weight"]), (0, 0, 0)
		)
