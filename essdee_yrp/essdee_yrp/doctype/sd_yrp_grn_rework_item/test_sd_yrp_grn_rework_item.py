from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_grn_rework_item import (
	sd_yrp_grn_rework_item as grn_rework_item,
)
from essdee_yrp.finishing import rebuild


class TestGRNReworkItem(IntegrationTestCase):
	def test_size_sort_matches_ipd_order_shape(self):
		values = ["80 cm", "45 cm", "S", "50 cm"]
		self.assertEqual(
			sorted(values, key=grn_rework_item._size_sort_key),
			["45 cm", "50 cm", "80 cm", "S"],
		)

	def test_source_warehouse_follows_completed_internal_transfer(self):
		parent = frappe._dict(warehouse="Transit", grn_number="GRN-1")
		row = frappe._dict(item_variant="Variant-1")
		balances = {"Transit": 0, "Final": 2}
		with patch.object(
			grn_rework_item.frappe.db,
			"get_value",
			return_value="Final",
		):
			warehouse = grn_rework_item._source_warehouse(
				parent,
				row,
				{"lot": "LOT-1", "received_type": "Adas"},
				1,
				lambda _item, candidate, **_dims: balances[candidate],
			)
		self.assertEqual(warehouse, "Final")

	def test_conversion_posts_equal_value_received_type_transfer(self):
		parent = frappe._dict(
			name="RW-TEST",
			lot="LOT-1",
			warehouse="Transit",
			grn_number=None,
		)
		row = frappe._dict(
			name="ROW-1",
			item_variant="Variant-1",
			received_type="Adas",
			uom="Pieces",
			source_grn_item=None,
		)

		def cached_value(doctype, _name, fieldname):
			if doctype == 'YRP Item Variant':
				return "Item-1"
			if doctype == 'YRP Item' and fieldname == "default_unit_of_measure":
				return "Pieces"
			return None

		with (
			patch("yrp.stock.dimensions.get_dimension_fieldnames", return_value=["lot", "received_type"]),
			patch("yrp.stock.utils.get_last_sle_rate", return_value=(13.5, True)),
			patch("yrp.stock.utils.get_stock_balance", return_value=4),
			patch("yrp.stock.stock_ledger.make_sl_entries") as make_entries,
			patch.object(grn_rework_item.frappe, "get_cached_value", side_effect=cached_value),
		):
			grn_rework_item._post_conversions(parent, [(row, "Accepted", 1)])

		entries = make_entries.call_args.args[0]
		self.assertEqual(len(entries), 2)
		self.assertEqual(entries[0]["qty"], -1)
		self.assertEqual(entries[0]["received_type"], "Adas")
		self.assertEqual(entries[0]["outgoing_rate"], 13.5)
		self.assertEqual(entries[1]["qty"], 1)
		self.assertEqual(entries[1]["received_type"], "Accepted")
		self.assertEqual(entries[1]["rate"], 0)
		self.assertEqual(entries[0]["_transfer_key"], entries[1]["_transfer_key"])
		make_entries.assert_called_once_with(entries, force_inline=True)

	def test_finishing_ignores_provisional_rejection(self):
		row = frappe._dict(
			item_variant="Variant-1",
			set_combination="{}",
			quantity=3,
			rejection=2,
			completed=0,
		)
		doc = frappe._dict(
			grn_number="GRN-1",
			grn_rework_item_details=[row],
			grn_reworked_item_details=[],
		)
		with (
			patch.object(rebuild.frappe, "get_all", side_effect=[["RW-1"], []]),
			patch.object(rebuild.frappe, "get_doc", return_value=doc),
			patch.object(rebuild.frappe.db, "get_value", return_value=0),
		):
			values = rebuild._collect_rework("LOT-1", {}, "Accepted", "Rejected")
		self.assertEqual(next(iter(values.values()))["rejected_qty"], 0)
