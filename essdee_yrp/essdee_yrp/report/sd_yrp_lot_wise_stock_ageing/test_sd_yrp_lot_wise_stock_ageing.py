from datetime import datetime, timedelta

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.report.sd_yrp_lot_wise_stock_ageing.sd_yrp_lot_wise_stock_ageing import (
	FIFOSlots,
	attach_item_details,
	order_within_second,
)


def ledger_row(name, second, micro, created, qty):
	return frappe._dict(
		name=name,
		posting_datetime=datetime(2026, 1, 1, 10, 0, second),
		posting_time=timedelta(hours=10, seconds=second, microseconds=micro),
		creation=datetime(2026, 1, 1, 10, 0, created),
		qty=qty,
	)


class TestLotWiseStockAgeing(IntegrationTestCase):
	def test_order_within_second_matches_posting_time_creation_qty(self):
		rows = [
			ledger_row("late-micro", 1, 900, 1, 5),
			ledger_row("early-micro", 1, 100, 9, 5),
			ledger_row("same-time-negative", 1, 100, 9, -3),
			ledger_row("next-second", 2, 0, 0, 1),
		]
		ordered = [row.name for row in order_within_second(iter(rows))]
		self.assertEqual(ordered, ["same-time-negative", "early-micro", "late-micro", "next-second"])

	def test_order_within_second_mixes_exact_and_truncated_datetimes(self):
		exact = ledger_row("exact-early", 1, 200, 1, 5)
		exact.posting_datetime = exact.posting_datetime.replace(microsecond=200)
		truncated = ledger_row("truncated-late", 1, 700, 0, 5)
		ordered = [row.name for row in order_within_second(iter([truncated, exact]))]
		self.assertEqual(ordered, ["exact-early", "truncated-late"])

	def test_attach_item_details_drops_unknown_items(self):
		items = {
			"Fabric-M": {"item_name": "Fabric", "stock_uom": "Kg", "brand": None, "item_group": "Fabric"}
		}
		rows = [frappe._dict(name="Fabric-M", qty=1), frappe._dict(name="Missing", qty=2)]
		joined = list(attach_item_details(rows, items))
		self.assertEqual(
			[(row.name, row.item_name, row.stock_uom) for row in joined], [("Fabric-M", "Fabric", "Kg")]
		)

	def test_streamed_ledger_follows_sql_posting_order(self):
		lot = frappe.db.get_value("YRP Stock Ledger Entry", {"is_cancelled": 0, "lot": ["is", "set"]}, "lot")
		if not lot:
			self.skipTest("No stock ledger entries with a lot")
		filters = frappe._dict(to_date="2099-12-31", lot=lot)
		streamed = list(FIFOSlots(filters)._FIFOSlots__get_stock_ledger_entries())
		expected = frappe.db.sql(
			"""SELECT sle.qty, sle.posting_date, sle.voucher_no FROM `tabYRP Stock Ledger Entry` sle
			JOIN `tabItem` variant ON variant.name = sle.item
			JOIN `tabItem` item ON item.name = COALESCE(NULLIF(variant.variant_of, ''), variant.name)
			WHERE sle.lot = %s AND sle.is_cancelled != 1
			ORDER BY sle.posting_date, sle.posting_time, sle.creation, sle.qty""",
			lot,
			as_dict=True,
		)
		self.assertEqual(
			[(row.qty, row.posting_date, row.voucher_no) for row in streamed],
			[(row.qty, row.posting_date, row.voucher_no) for row in expected],
		)
