from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase


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
				"yrp.stock.utils.get_conversion_factor",
				return_value={"stock_uom": "Kg", "conversion_factor": 1},
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
			uom="Kg",
		)
		self.assertEqual(row.rate, 130)
		self.assertEqual(row.stock_qty, 2)
		self.assertEqual(row.stock_uom_rate, 130)
		self.assertEqual(row.amount, 260)
