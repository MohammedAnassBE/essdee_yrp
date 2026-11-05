from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.finishing.packing import get_box_packing


def make_ipd(**values):
	defaults = {
		"packing_combo": 10,
		"based_on_other_attribute_mapping": 0,
		"packing_mode": "",
		"packing_attribute_details": [],
	}
	defaults.update(values)
	return frappe._dict(defaults)


def detail(colour, quantity):
	return frappe._dict(attribute_value=f"IAV-{colour}", quantity=quantity)


class TestFinishingBoxPacking(TestCase):
	def setUp(self):
		resolver = patch(
			"essdee_yrp.finishing.packing._attribute_value", side_effect=lambda raw: raw.removeprefix("IAV-")
		)
		resolver.start()
		self.addCleanup(resolver.stop)

	def test_packing_combo_is_pieces_per_box_with_the_colour_ratio(self):
		ipd = make_ipd(
			packing_combo=5,
			packing_attribute_details=[detail("Red", 3), detail("Blue", 2), detail("Green", 0)],
		)
		self.assertEqual(get_box_packing(ipd), {"pieces_per_box": 5, "colour_ratio": {"Red": 3, "Blue": 2}})

	def test_zero_colour_quantities_give_no_ratio(self):
		ipd = make_ipd(packing_attribute_details=[detail("Red", 0), detail("Blue", 0)])
		self.assertEqual(get_box_packing(ipd), {"pieces_per_box": 10, "colour_ratio": {}})

	def test_missing_packing_combo_is_unknown(self):
		self.assertEqual(get_box_packing(make_ipd(packing_combo=None))["pieces_per_box"], 0)

	def test_size_ratio_packing_has_no_single_pieces_per_box(self):
		ipd = make_ipd(based_on_other_attribute_mapping=1, packing_mode="Size Ratio Packing")
		self.assertEqual(get_box_packing(ipd)["pieces_per_box"], 0)
