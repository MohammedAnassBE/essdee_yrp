import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot import sd_yrp_lot
from essdee_yrp.essdee_yrp.doctype.sd_yrp_lot.sd_yrp_lot import _build_bom_summary_json

PRINT_FORMAT = "Essdee Lot BOM"


def _bom_row(item, mapped=False, process="Packing", stage="Piece", qty_of_product=1, qty_of_bom=1):
	return frappe._dict(
		item=item,
		based_on_attribute_mapping=int(mapped),
		process_name=process,
		dependent_attribute_value=stage,
		qty_of_product=qty_of_product,
		qty_of_bom_item=qty_of_bom,
	)


def _accessory(item, variant, qty, demand_index=0, qty_of_bom=1, uom="Nos"):
	return {
		"item": item,
		"item_variant": variant,
		"required_qty": qty,
		"uom": uom,
		"qty_of_bom_item": qty_of_bom,
		"first_demand_index": demand_index,
	}


class TestLotBomPrint(FrappeTestCase):
	def test_summary_matches_production_api_template_item_shape(self):
		ipd = frappe._dict(
			dependent_attribute_mapping="_Test Stage Mapping",
			item_bom=[
				_bom_row("Size Label", mapped=True, process="Stitching"),
				_bom_row("Top Box", stage="Pack", qty_of_product=5),
				_bom_row("Fusing Sticker", mapped=True, process="Yolk Fusing"),
				_bom_row("Unmatched Badge", mapped=True),
				_bom_row("Top Box", process="Ironing", qty_of_product=9),
			],
		)
		accessories = [
			_accessory("Size Label", "Size Label-S", 40, demand_index=1, qty_of_bom=2),
			_accessory("Size Label", "Size Label-M", 60, demand_index=2, qty_of_bom=3),
			_accessory("Top Box", "Top Box", 20),
			_accessory("Top Box", "Top Box", 11),
			_accessory("Fusing Sticker", "Fusing Sticker-S", 100),
		]
		stages = {"attr_list": {"Piece": {"uom": "Pieces"}, "Pack": {"uom": "Box"}}}
		lot = frappe._dict(production_detail="_Test IPD")

		with (
			patch.object(frappe, "get_cached_doc", return_value=ipd),
			patch.object(sd_yrp_lot, "get_dependent_attribute_details", return_value=stages),
		):
			summary = _build_bom_summary_json(lot, accessories)

		self.assertEqual(list(summary), ["Top Box", "Fusing Sticker", "Size Label"])
		self.assertEqual(summary["Top Box"], ["Packing", 5, "Box", 1, "Nos", 31])
		self.assertEqual(summary["Fusing Sticker"], ["Yolk Fusing", 1, "Pieces", 1, "Nos", 100])
		self.assertEqual(summary["Size Label"], ["Stitching", 1, "Pieces", 2, "Nos", 100])

	def test_print_renders_bom_summary_rows(self):
		lot = frappe.get_doc(
			{
				"doctype": "SD YRP Lot",
				"name": "_Test Lot BOM Print",
				"item": "_Test Garment",
				"total_order_quantity": 1200,
				"bom_summary_json": json.dumps(
					{"_Test Top Box": ["Packing", 5.0, "Pieces", 1.0, "Nos", 240.0]}
				),
			}
		)
		html = frappe.get_print("SD YRP Lot", lot.name, PRINT_FORMAT, doc=lot)

		self.assertIn("Bom Summary", html)
		self.assertIn("<strong>_Test Top Box</strong>", html)
		self.assertIn("5.0 Pieces", html)
		self.assertIn("1.0 Nos", html)
		self.assertIn("240.0", html)
		self.assertIn(": 1200", html)

	def test_print_without_bom_or_ipd_renders_header_only(self):
		lot = frappe.get_doc(
			{"doctype": "SD YRP Lot", "name": "_Test Lot Without BOM", "item": "_Test Garment"}
		)
		html = frappe.get_print("SD YRP Lot", lot.name, PRINT_FORMAT, doc=lot)

		self.assertIn("Lot Number", html)
		self.assertNotIn("Bom Summary", html)

	def test_print_renders_real_lots_with_mapping_details(self):
		names = frappe.get_all(
			"SD YRP Lot",
			filters={"bom_summary_json": ["is", "set"], "production_detail": ["is", "set"]},
			pluck="name",
			order_by="modified desc",
			limit=3,
		)
		if not names:
			self.skipTest("No calculated Lots on this site.")
		for name in names:
			lot = frappe.get_doc("SD YRP Lot", name)
			html = frappe.get_print("SD YRP Lot", name, PRINT_FORMAT, doc=lot)
			for item in json.loads(lot.bom_summary_json):
				self.assertIn(f"<strong>{item}</strong>", html)
