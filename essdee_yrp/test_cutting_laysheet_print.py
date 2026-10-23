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

	def test_cutting_plan_print_resolves_cloth_rows_in_one_query(self):
		doc = frappe.get_doc(
			{
				"doctype": "SD YRP Cutting Plan",
				"cutting_plan_cloth_details": [{"colour": "IAV-BLACK", "dia": "IAV-DIA-60"}],
				"cutting_plan_accessory_details": [{"colour": "IAV-RED", "dia": "IAV-DIA-60"}],
			}
		)
		rows = [
			frappe._dict(name="IAV-BLACK", attribute_name="Colour", attribute_value="Black"),
			frappe._dict(name="IAV-RED", attribute_name="Colour", attribute_value="Red"),
			frappe._dict(name="IAV-DIA-60", attribute_name="Dia", attribute_value="60 Dia"),
		]
		get_all = frappe.get_all
		value_queries = []

		def fake_get_all(doctype, *args, **kwargs):
			if doctype != "YRP Item Attribute Value":
				return get_all(doctype, *args, **kwargs)
			value_queries.append(kwargs["filters"])
			return rows

		with (
			patch.object(frappe.local, "attribute_link_values", {}, create=True),
			patch("essdee_yrp.merch.ipd.payload.frappe.get_all", side_effect=fake_get_all),
		):
			doc.run_method("before_print")

		self.assertEqual(value_queries, [{"name": ["in", ["IAV-BLACK", "IAV-DIA-60", "IAV-RED"]]}])
		cloth, accessory = doc.cutting_plan_cloth_details[0], doc.cutting_plan_accessory_details[0]
		self.assertEqual((cloth.colour, cloth.dia), ("Black", "60 Dia"))
		self.assertEqual((accessory.colour, accessory.dia), ("Red", "60 Dia"))
