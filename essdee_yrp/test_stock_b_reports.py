"""Stock report arithmetic and read-only query checks."""

import unittest

import frappe

from essdee_yrp.essdee_yrp.report.sd_yrp_stock_entry_report import sd_yrp_stock_entry_report as entry
from essdee_yrp.essdee_yrp.report.sd_yrp_stock_item_balance_difference import (
	sd_yrp_stock_item_balance_difference as difference,
)
from essdee_yrp.essdee_yrp.report.sd_yrp_stock_reconciliation_report import (
	sd_yrp_stock_reconciliation_report as reconciliation,
)
from essdee_yrp.essdee_yrp.report.sd_yrp_stock_update_report import sd_yrp_stock_update_report as update


class TestStockBReports(unittest.TestCase):
	def test_stock_update_add_reduce_and_missing_quantities(self):
		self.assertEqual(update.stock_after("Add", 10, 4), 14)
		self.assertEqual(update.stock_after("Reduce", 10, 4), 6)
		self.assertEqual(update.stock_after("Reduce", None, 4), -4)
		self.assertEqual(update.stock_after("Add", 10, None), 10)

	def test_difference_aggregates_both_sides_and_keeps_distinct_keys(self):
		def row(item, warehouse, quantity):
			return {
				"item": item,
				"parent_item": "Fabric",
				"warehouse": warehouse,
				"lot": "L1",
				"received_type": "Accepted",
				"quantity": quantity,
			}

		bins = [row("AB", "C", 3), row("AB", "C", 2), row("A", "BC", 7), row("bin-only", "C", 4)]
		ledger = [row("AB", "C", 12), row("AB", "C", -2), row("A", "BC", 7), row("ledger-only", "C", 2)]
		result = {r["item"]: r for r in difference.merge_balances(bins, ledger)}
		self.assertEqual(
			(result["AB"]["item_bal"], result["AB"]["stock_bal"], result["AB"]["diff_between"]), (5, 10, 5)
		)
		self.assertEqual(result["A"]["diff_between"], 0)
		self.assertEqual(result["bin-only"]["diff_between"], -4)
		self.assertEqual(result["ledger-only"]["diff_between"], 2)
		self.assertEqual(len(difference.merge_balances(bins, ledger, remove_zero=True)), 3)

	@unittest.skipUnless(getattr(frappe.local, "site", None), "Requires a connected migration snapshot")
	def test_entry_filters_template_and_variant(self):
		filters = {
			"from_date": "2026-09-01",
			"to_date": "2026-09-01",
			"item_variant": "535473 - LADIES CREAM XMAS DOGS AOP B-20-22-White Cream Dogs AOP-Front Placket Left",
		}
		rows = entry.execute(filters)[1]
		self.assertTrue(rows)
		self.assertTrue(all(row["item_variant"] == filters["item_variant"] for row in rows))
		self.assertTrue(all(row["item"] == "535473 - LADIES CREAM XMAS DOGS AOP B" for row in rows))
		self.assertEqual(entry.execute({**filters, "item": "Thermal Fabric"})[1], [])

	@unittest.skipUnless(getattr(frappe.local, "site", None), "Requires a connected migration snapshot")
	def test_reconciliation_difference_uses_previous_stock(self):
		rows = reconciliation.execute(
			{
				"from_date": "2026-09-03",
				"to_date": "2026-09-03",
				"item_variant": "AISHWARYA PRINT-80 cm",
				"lot": "F0326-62/5",
			}
		)[1]
		self.assertEqual(len(rows), 2)
		by_voucher = {row["stock_reconciliation"]: row for row in rows}
		row = by_voucher["ST-RECO-2026-00294"]
		self.assertEqual(
			(
				row["stock_reconciliation"],
				row["previous_quantity"],
				row["updated_quantity"],
				row["difference"],
			),
			("ST-RECO-2026-00294", 1000, 800, -200),
		)
		self.assertEqual(row["previous_queue"], "[[1000.0, -17.015288757]]")
		self.assertEqual(row["previous_rate"], -17.015288757)
		row = by_voucher["ST-RECO-2026-00295"]
		self.assertEqual(
			(row["previous_quantity"], row["updated_quantity"], row["difference"]), (800, 1000, 200)
		)

	@unittest.skipUnless(getattr(frappe.local, "site", None), "Requires a connected migration snapshot")
	def test_difference_does_not_rewrite_variant_filter(self):
		filters = {
			"from_date": "2026-09-01",
			"to_date": "2026-09-30",
			"item": "Thermal Fabric-36 Dia-Andhra Melange",
			"warehouse": "S-0005",
		}
		original = dict(filters)
		rows = difference.execute(filters)[1]
		self.assertEqual(filters, original)
		self.assertTrue(rows)
		self.assertTrue(all(row["item"] == original["item"] for row in rows))

	@unittest.skipUnless(getattr(frappe.local, "site", None), "Requires a connected migration snapshot")
	def test_update_standalone_item_is_its_own_parent(self):
		rows = update.execute(
			{"from_date": "2026-09-01", "to_date": "2026-09-30", "item": "Myntra Inner Pad"}
		)[1]
		self.assertEqual(len(rows), 1)
		self.assertEqual(
			(rows[0]["item"], rows[0]["item_variant"], rows[0]["stock_after"]),
			("Myntra Inner Pad", "Myntra Inner Pad", 484),
		)
