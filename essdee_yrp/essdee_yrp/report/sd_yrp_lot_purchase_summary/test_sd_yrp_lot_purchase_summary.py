from datetime import datetime

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.report.sd_yrp_lot_purchase_summary.sd_yrp_lot_purchase_summary import (
	get_latest_balances,
	get_stock_data,
)

EARLY = datetime(2026, 1, 1, 10, 0, 0, 100)
LATE = datetime(2026, 1, 1, 10, 0, 0, 200)
LATER = datetime(2026, 1, 2)


class TestSDYRPLotPurchaseSummary(IntegrationTestCase):
	def test_latest_active_time_wins(self):
		entries = [
			("ITEM", "WH", "LOT", LATE, 7.0, 1),
			("ITEM", "WH", "LOT", EARLY, 3.0, 1),
			("ITEM", "WH", "LOT", LATER, 9.0, 0),
		]
		self.assertEqual(list(get_latest_balances(entries)), [(("ITEM", "WH", "LOT"), 7.0)])

	def test_cancelled_row_at_latest_time_is_kept(self):
		entries = [
			("ITEM", "WH", "LOT", LATE, 2.0, 0),
			("ITEM", "WH", "LOT", EARLY, 1.0, 1),
			("ITEM", "WH", "LOT", LATE, 5.0, 1),
		]
		self.assertEqual(
			sorted(qty for _key, qty in get_latest_balances(entries)),
			[2.0, 5.0],
		)

	def test_bucket_with_only_cancelled_rows_is_skipped(self):
		self.assertEqual(list(get_latest_balances([("ITEM", "WH", "LOT", LATE, 4.0, 0)])), [])

	def test_stock_data_matches_grouped_ledger_query(self):
		lot = frappe.db.get_value("YRP Stock Ledger Entry", {"is_cancelled": 0}, "lot", order_by="creation desc")
		if not lot:
			self.skipTest("No stock ledger entries")
		expected = frappe.db.sql(
			"""
			select sle.item, sle.warehouse, sle.lot, sle.qty_after_transaction as qty
			from `tabYRP Stock Ledger Entry` sle
			join (
				select item, warehouse, lot, max(timestamp(posting_date, posting_time)) as latest_at
				from `tabYRP Stock Ledger Entry`
				where docstatus < 2 and is_cancelled = 0 and lot = %(lot)s
				group by item, warehouse, lot
			) latest on latest.item = sle.item and latest.warehouse = sle.warehouse
				and latest.lot = sle.lot and latest.latest_at = timestamp(sle.posting_date, sle.posting_time)
			join `tabWarehouse` warehouse on warehouse.name = sle.warehouse
			join `tabItem` item on item.name = sle.item
			""",
			{"lot": lot},
			as_dict=True,
		)
		actual = get_stock_data(frappe._dict(lot=lot))

		def key(row):
			return (row.item, row.warehouse, row.lot, row.qty)

		self.assertEqual(sorted(map(key, actual)), sorted(map(key, expected)))
