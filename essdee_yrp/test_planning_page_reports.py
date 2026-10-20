"""Planning page quantity and matrix regressions."""

import unittest
from unittest.mock import patch

import frappe

from essdee_yrp.essdee_yrp.report.sd_yrp_supplier_pending_report import (
	sd_yrp_supplier_pending_report as supplier,
)


class TestPlanningPageReports(unittest.TestCase):
	def test_supplier_boundary_and_set_part_totals(self):
		orders = [
			{
				"name": "WO",
				"item": "Shirt",
				"lot": "LOT",
				"first_dc_date": "2026-01-01",
				"last_dc_date": "2026-01-04",
				"last_grn_date": "2026-01-07",
			}
		]
		context = {
			"LOT": {
				"primary_item_attribute": "Size",
				"packing_attribute": "Colour",
				"is_set_item": 1,
				"set_item_attribute": "Part",
				"major_attribute_value": "Top",
				"primary_values": ["S", "M"],
			}
		}
		calculated = [
			{
				"parent": "WO",
				"item_variant": "V1",
				"delivered_quantity": 100,
				"received_qty": 90,
				"set_combination": '{"major_colour":"Navy"}',
			},
			{"parent": "WO", "item_variant": "V2", "delivered_quantity": 100, "received_qty": 91},
		]
		attrs = {
			"V1": {"Size": "S", "Colour": "Red", "Part": "Bottom"},
			"V2": {"Size": "M", "Colour": "Blue", "Part": "Top"},
		}
		items = supplier._build_supplier_pending_items(orders, calculated, context, attrs)
		lot = items[0]["lots"][0]
		self.assertEqual(len(lot["rows"]), 1)
		self.assertEqual(lot["rows"][0]["colour"], "Red(Navy)")
		self.assertEqual(lot["rows"][0]["dates"]["diff_days"], 3)
		self.assertEqual(lot["totals"][0]["values"]["S"]["difference"], -10)
		_columns, rows = supplier.to_desk(items)
		self.assertEqual([r["type"] for r in rows], ["Delivered", "Received", "Difference"] * 2)
		self.assertEqual([r["size_1"] for r in rows], [0] * 6)
		self.assertEqual([r["total"] for r in rows], [100, 90, -10] * 2)

	def test_pending_boundary_requires_delivery(self):
		self.assertTrue(supplier._row_is_pending(100, 90))
		self.assertFalse(supplier._row_is_pending(100, 90.01))
		self.assertFalse(supplier._row_is_pending(0, 0))
		self.assertFalse(supplier._row_is_pending(-1, 0))

	def test_empty_response_keeps_fixed_columns(self):
		columns, rows = supplier.to_desk([])
		self.assertEqual(rows, [])
		self.assertEqual(
			[column["fieldname"] for column in columns],
			["item", "lot", "serial_no", "colour", "type", "total", "first_date", "last_date", "diff_days"],
		)

	def test_unconfigured_sizes_are_sorted_after_configured_sizes(self):
		orders = [{"name": "WO", "item": "Shirt", "lot": "LOT"}]
		calculated = [
			{"parent": "WO", "item_variant": variant, "delivered_quantity": 10, "received_qty": 1}
			for variant in ("XL", "L")
		]
		context = {
			"LOT": {
				"primary_item_attribute": "Size",
				"packing_attribute": "Colour",
				"is_set_item": 0,
				"primary_values": ["S", "M"],
			}
		}
		items = supplier._build_supplier_pending_items(
			orders,
			calculated,
			context,
			{variant: {"Size": variant, "Colour": "Blue"} for variant in ("XL", "L")},
		)
		self.assertEqual(items[0]["lots"][0]["primary_values"], ["S", "M", "L", "XL"])
		columns, rows = supplier.to_desk(items)
		self.assertEqual(rows[0]["total"], 20)
		self.assertEqual(rows[0]["first_date"], None)
		self.assertNotIn("part", [column["fieldname"] for column in columns])

	def test_lot_contexts_resolve_scoped_titles_in_bulk(self):
		def get_all(doctype, **kwargs):
			rows = {
				"SD YRP Lot": [
					{"name": "LOT1", "production_detail": "IPD"},
					{"name": "LOT2", "production_detail": "IPD"},
				],
				"YRP Item Production Detail": [
					{"name": "IPD", "primary_item_attribute": "Size", "major_attribute_value": "IAV-TOP"}
				],
				"YRP IPD Item Attribute": [{"parent": "IPD", "attribute": "Size", "mapping": "MAP"}],
				"YRP Item Item Attribute Mapping Value": [
					{"parent": "MAP", "attribute_value": "IAV-S"},
					{"parent": "MAP", "attribute_value": "IAV-M"},
				],
				"YRP Item Attribute Value": [
					{"name": "IAV-TOP", "attribute_value": "Top"},
					{"name": "IAV-S", "attribute_value": "S"},
					{"name": "IAV-M", "attribute_value": "M"},
				],
			}
			return [frappe._dict(row) for row in rows[doctype]]

		with patch.object(frappe, "get_all", side_effect=get_all):
			contexts = supplier._load_lot_contexts(["LOT1", "LOT2"])
		self.assertEqual(contexts["LOT1"]["major_attribute_value"], "Top")
		self.assertEqual(contexts["LOT2"]["primary_values"], ["S", "M"])

	def test_desk_sizes_do_not_shift_between_lots(self):
		items = []
		for number, size in enumerate(("S", "XL")):
			items.extend(
				supplier._build_supplier_pending_items(
					[{"name": "WO", "item": "Shirt", "lot": f"LOT{number}"}],
					[{"parent": "WO", "item_variant": "V", "delivered_quantity": 10, "received_qty": 2}],
					{
						f"LOT{number}": {
							"primary_item_attribute": "Size",
							"packing_attribute": "Colour",
							"primary_values": [size],
						}
					},
					{"V": {"Size": size, "Colour": "Navy"}},
				)
			)
		columns, rows = supplier.to_desk(items)
		self.assertEqual(
			[column["label"] for column in columns if column["fieldname"].startswith("size_")], ["S", "XL"]
		)
		self.assertEqual((rows[0]["size_0"], rows[0]["size_1"]), (10, 0))
		self.assertEqual((rows[6]["size_0"], rows[6]["size_1"]), (0, 10))
