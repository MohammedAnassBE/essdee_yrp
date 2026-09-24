from unittest import TestCase
from unittest.mock import patch

import frappe
from essdee_yrp.essdee_yrp.doctype.sd_yrp_cutting_laysheet import sd_yrp_cutting_laysheet as cutting


class TestCuttingAccessoryReceipts(TestCase):
	def test_accessory_receipt_is_added_with_empty_combination(self):
		lay = frappe._dict(
			cutting_laysheet_bundles=[],
			cutting_laysheet_accessory_details=[
				frappe._dict(cloth_item_variant="FOLDING-GREY", weight=20),
				frappe._dict(cloth_item_variant="FOLDING-GREY", weight=5),
			],
		)
		defaults = {"items": [dict(item_variant="FOLDING-GREY", quantity=0, received_type="Accepted", set_combination="{}", ref_docname="WO-ACCESSORY")]}
		with (
			patch.object(cutting.frappe, "get_value", return_value=("Size", "Colour", "Panel", "Cut", "Stage")),
			patch.object(cutting.frappe, "get_cached_doc", return_value=frappe._dict(stiching_item_details=[])),
			patch.object(cutting.frappe.db, "get_single_value", return_value="Accepted"),
			patch("yrp.yrp.doctype.yrp_goods_received_note.yrp_goods_received_note.get_work_order_defaults", return_value=defaults),
			patch("essdee_yrp.overrides.goods_received_note.normalize_cutting_grn_row_indexes", side_effect=lambda rows: rows),
		):
			_, rows = cutting._cutting_grn_output_rows(lay, frappe._dict(name="WO"), "Garment", "IPD")
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].quantity, 25)
		self.assertEqual(rows[0].ref_docname, "WO-ACCESSORY")

	def test_accessory_value_is_not_distributed_to_panels(self):
		accessory = frappe._dict(name="ACCESSORY", stock_qty=20)
		panels = [frappe._dict(name="FRONT", stock_qty=100), frappe._dict(name="BACK", stock_qty=100)]
		allocations = cutting._allocate_cutting_input(20, 20, [accessory], panels)
		self.assertEqual([(r.name, q) for r, q in allocations], [("ACCESSORY", 20)])
		self.assertEqual(sum(q * 320 for _, q in allocations), 6400)

	def test_same_fabric_can_supply_panels_and_accessory(self):
		accessory = frappe._dict(name="ACCESSORY", stock_qty=20)
		panels = [frappe._dict(name="FRONT", stock_qty=1), frappe._dict(name="BACK", stock_qty=2)]
		allocations = cutting._allocate_cutting_input(50, 20, [accessory], panels)
		self.assertEqual([(r.name, q) for r, q in allocations], [("ACCESSORY", 20), ("FRONT", 10), ("BACK", 20)])
		self.assertEqual(sum(q for _, q in allocations), 50)

	def test_missing_accessory_receipt_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			cutting._allocate_cutting_input(20, 20, [], [frappe._dict(stock_qty=100)])
