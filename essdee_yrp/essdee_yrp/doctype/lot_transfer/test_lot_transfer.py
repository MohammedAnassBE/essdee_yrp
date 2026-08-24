from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.lot_transfer.lot_transfer import LotTransfer


class TestLotTransfer(IntegrationTestCase):
	def test_valuation_lookup_passes_stock_dimensions_by_name(self):
		transfer = frappe.new_doc("Lot Transfer")
		transfer.posting_date = "2026-07-29"
		transfer.posting_time = "12:34:56"
		row = frappe._dict(
			{
				"idx": 1,
				"item": "_Test Lot Transfer Variant",
				"from_lot": "LOT-A",
				"to_lot": "LOT-B",
				"warehouse": "Main Warehouse",
				"received_type": "Accepted",
				"qty": 2,
				"uom": "Kg",
				"rate": 0,
			}
		)

		with (
			patch(
				"frappe.db.get_value",
				return_value="_Test Lot Transfer Item",
			),
			patch(
				"yrp.yrp.doctype.item.item.validate_disabled",
			),
			patch(
				"yrp.yrp.doctype.item.item.validate_is_stock_item",
			),
			patch(
				"yrp.yrp.doctype.item.item.validate_cancelled_item",
			),
			patch(
				"yrp.stock.uom.resolve_item_uom",
				return_value=frappe._dict(
					uom="Kg", stock_uom="Kg", conversion_factor=1
				),
			),
			patch(
				"yrp.stock.dimensions.get_dimension_fieldnames",
				return_value=["lot", "received_type"],
			),
			patch(
				"yrp.stock.utils.get_stock_balance",
				return_value=(6.67, 130),
			) as get_stock_balance,
		):
			transfer._validate_row(row)

		get_stock_balance.assert_called_once_with(
			"_Test Lot Transfer Variant",
			"Main Warehouse",
			posting_date="2026-07-29",
			posting_time="12:34:56",
			with_valuation_rate=True,
			lot="LOT-A",
			received_type="Accepted",
		)
		self.assertEqual(row.rate, 130)
		self.assertEqual(row.stock_qty, 2)
		self.assertEqual(row.stock_uom_rate, 130)
		self.assertEqual(row.amount, 260)

	def test_stock_rows_are_an_exact_paired_value_neutral_transfer(self):
		transfer = LotTransfer(
			{
				"doctype": "Lot Transfer",
				"name": "LT-TEST",
				"posting_date": "2026-07-29",
				"posting_time": "12:34:56",
			}
		)
		row = frappe._dict(
			name="LT-ROW-1",
			item="ITEM-VARIANT",
			warehouse="Main Warehouse",
			from_lot="LOT-A",
			to_lot="LOT-B",
			received_type="Accepted",
			stock_qty=2,
			stock_uom="Kg",
			stock_uom_rate=130,
		)

		with patch(
			"yrp.stock.dimensions.get_dimension_fieldnames",
			return_value=["lot", "received_type"],
		):
			outgoing = transfer._stock_row(
				row, row.from_lot, -2, 0, "pair-1", "outgoing"
			)
			incoming = transfer._stock_row(
				row, row.to_lot, 2, 130, "pair-1", "incoming"
			)

		self.assertEqual(outgoing._transfer_key, incoming._transfer_key)
		self.assertEqual(outgoing._transfer_role, "outgoing")
		self.assertEqual(incoming._transfer_role, "incoming")
		self.assertEqual(outgoing.qty + incoming.qty, 0)
		self.assertEqual(outgoing.lot, "LOT-A")
		self.assertEqual(incoming.lot, "LOT-B")
		self.assertEqual(outgoing.received_type, incoming.received_type)
