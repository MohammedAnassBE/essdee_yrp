from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet import (
	get_bundle_items,
)


class BundleRow(dict):
	def __getattr__(self, key):
		return self.get(key)

	def as_dict(self):
		return dict(self)


LABELS = {"IAV-SIZE-75": "75 cm", "IAV-SIZE-80": "80 cm", "IAV-BLACK": "Black"}


def _laysheet():
	totals = dict.fromkeys(
		(
			"width",
			"width_allowance",
			"length",
			"length_allowance",
			"piece_weight",
			"no_of_rolls",
			"weight",
			"no_of_bits",
			"end_bit_weight",
			"accessory_weight",
			"total_used_weight",
			"required_pcs_weight",
		),
		0,
	)
	return frappe.get_doc(
		{
			"doctype": "SD YRP Cutting LaySheet",
			"name": "CLS-PRINT-TEST",
			"creation": "2026-09-01 10:00:00",
			"selected_type": "Machine",
			**totals,
			"cutting_marker_ratios": [
				{"size": "IAV-SIZE-75", "ratio": 1, "panel": "Front"},
				{"size": "IAV-SIZE-80", "ratio": 2, "panel": "Front"},
				{"size": "IAV-SIZE-75", "ratio": 1, "panel": "Back"},
			],
			"cutting_laysheet_details": [{"colour": "IAV-BLACK", "shade": "A", "weight": 10}],
		}
	)


class TestCuttingLaySheetPrint(TestCase):
	def test_laysheet_print_shows_attribute_values_in_marker_order(self):
		with patch(
			"essdee_yrp.print_helpers._attribute_value",
			side_effect=lambda value: LABELS.get(value, value),
		):
			html = frappe.get_print(
				"SD YRP Cutting LaySheet",
				"CLS-PRINT-TEST",
				"Essdee Cutting LaySheet",
				doc=_laysheet(),
				no_letterhead=1,
			)

		self.assertNotIn("IAV-", html)
		for section in (
			"Cutting Department LaySheet",
			"SIZES",
			"RATIO",
			"COLOR",
			"Total Used Weight",
			"APPROVED BY",
		):
			self.assertIn(section, html)
		self.assertLess(html.index(">75 cm<"), html.index(">80 cm<"))
		self.assertEqual(html.count(">75 cm<"), 1)
		self.assertIn(">Black<", html)

	def test_movement_chart_bundle_items_resolve_size_title(self):
		doc = frappe._dict(
			cutting_laysheet_bundles=[
				BundleRow(bundle_no=1, size="IAV-S", colour="IAV-NAVY", part="Back"),
				BundleRow(bundle_no=1, size="IAV-S", colour="IAV-NAVY", part="Front"),
				BundleRow(bundle_no=2, size="IAV-M", colour="IAV-NAVY", part="Back"),
			]
		)
		doc.check_permission = MagicMock()
		labels = {"IAV-S": "S", "IAV-M": "M"}
		with (
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet.frappe.get_doc",
				return_value=doc,
			),
			patch(
				"essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet.sd_yrp_cutting_laysheet._attribute_value",
				side_effect=lambda value: labels.get(value, value),
			),
		):
			items = get_bundle_items("CLS-TEST")

		self.assertEqual([item["size"] for item in items], ["S", "M"])
