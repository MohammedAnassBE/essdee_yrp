from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.cutting import cloth_usage
from essdee_yrp.cutting.cloth_usage import get_actual_cloth_type, get_cloth_keys
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_bulk_lay_sheets.sd_yrp_cutting_bulk_lay_sheets import (
	validate_cutting_plan_stock,
)
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet import sd_yrp_cutting_laysheet as laysheet_module
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	get_table_entries,
	validate_cutting_plan_cloth_balance,
)


def _plan_row(cloth_type, dia, weight, colour="Red", used_weight=0):
	return SimpleNamespace(
		colour=colour, cloth_type=cloth_type, dia=dia, weight=weight, used_weight=used_weight
	)


def _plan():
	"""Panels plan Main at 32 Dia; the Folding accessory fabric is 26 Dia."""
	return SimpleNamespace(
		cutting_plan_cloth_details=[_plan_row("Main", "32 Dia", 100), _plan_row("Folding", "26 Dia", 10)],
		save=MagicMock(),
	)


def _panel_row(weight, actual_dia="26 Dia"):
	return SimpleNamespace(
		name="ROW-1",
		colour="Red",
		cloth_type="Main",
		dia="32 Dia",
		actual_dia=actual_dia,
		weight=weight,
		balance_weight=0,
		used_weight=weight,
		cloth_item_variant="Main Cloth-Red-32 Dia",
	)


def _laysheet(row):
	return SimpleNamespace(
		name="CLS-TEST",
		cutting_plan="CP-TEST",
		cutting_laysheet_details=[row],
		cutting_laysheet_accessory_details=[],
	)


def _patch_plan(plan):
	get_doc = frappe.get_doc

	def fake_get_doc(doctype, *args, **kwargs):
		if doctype == "SD YRP Cutting Plan":
			return plan
		return get_doc(doctype, *args, **kwargs)

	return patch.object(frappe, "get_doc", side_effect=fake_get_doc)


class TestActualDiaClothType(IntegrationTestCase):
	"""An Actual Dia outside the row's cloth type draws from the plan fabric holding that dia."""

	def setUp(self):
		self.keys = get_cloth_keys(_plan().cutting_plan_cloth_details)

	def test_own_cloth_type_keeps_its_dia(self):
		self.assertEqual(get_actual_cloth_type(self.keys, "Red", "Main", "32 Dia"), "Main")

	def test_other_cloth_type_dia_resolves_to_that_fabric(self):
		self.assertEqual(get_actual_cloth_type(self.keys, "Red", "Main", "26 Dia"), "Folding")

	def test_dia_missing_for_colour_keeps_own_cloth_type(self):
		self.assertEqual(get_actual_cloth_type(self.keys, "Blue", "Main", "26 Dia"), "Main")

	def test_dia_held_by_two_other_cloth_types_fails_loudly(self):
		keys = self.keys | get_cloth_keys([_plan_row("Rib", "26 Dia", 5)])
		with self.assertRaises(frappe.ValidationError):
			get_actual_cloth_type(keys, "Red", "Main", "26 Dia")

	def test_bundle_generation_charges_the_folding_fabric_balance(self):
		with _patch_plan(_plan()):
			validate_cutting_plan_cloth_balance(_laysheet(_panel_row(8)), "CP-TEST")
			with self.assertRaises(frappe.ValidationError):
				validate_cutting_plan_cloth_balance(_laysheet(_panel_row(12)), "CP-TEST")

	def test_bulk_stock_check_reads_the_folding_fabric_balance(self):
		with _patch_plan(_plan()):
			validate_cutting_plan_stock(_laysheet(_panel_row(8)))
			with self.assertRaises(frappe.ValidationError):
				validate_cutting_plan_stock(_laysheet(_panel_row(12)))

	def test_dia_conversion_takes_stock_from_the_folding_cloth_item(self):
		ipd_doc = SimpleNamespace(
			packing_attribute="Colour",
			cloth_detail=[
				SimpleNamespace(name1="Main", cloth="Main Cloth"),
				SimpleNamespace(name1="Folding", cloth="Folding Cloth"),
			],
		)
		with (
			patch.object(
				laysheet_module, "get_or_create_variant", return_value="Folding Cloth-Red-26 Dia"
			) as variant,
			patch.object(laysheet_module, "get_sl_entries", side_effect=lambda variant, *args: variant),
			patch.object(laysheet_module, "get_dia_attribute", return_value="Dia"),
			patch.object(frappe, "get_cached_value", return_value="Kg"),
		):
			entries = get_table_entries(
				[_panel_row(8)], ipd_doc, "WH", "LOT", "CLS-TEST", "Accepted", -1, 1, self.keys
			)

		variant.assert_called_once_with("Folding Cloth", {"Colour": "Red", "Dia": "26 Dia"})
		self.assertEqual(entries, ["Folding Cloth-Red-26 Dia", "Main Cloth-Red-32 Dia"])

	def test_plan_usage_counts_the_cut_on_the_folding_fabric(self):
		row = frappe._dict(colour="Red", cloth_type="Main", dia="26 Dia", weight=8)
		with patch.object(frappe.db, "sql", return_value=[row]):
			usage = cloth_usage.get_laysheet_cloth_usage("CP-TEST", "actual_dia", self.keys)

		self.assertEqual(usage, {("Red", "Folding", "26 Dia"): 8})
