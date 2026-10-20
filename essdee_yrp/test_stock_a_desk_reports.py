"""Behavior checks for the Stock A Desk ports."""

from importlib import import_module
from unittest import TestCase
from unittest.mock import patch

import frappe


def report(name):
	return import_module(f"essdee_yrp.essdee_yrp.report.sd_yrp_{name}.sd_yrp_{name}")


class TestStockADeskReports(TestCase):
	def test_balance_filters_actual_quantity_and_keeps_reserved_balance(self):
		module = report("item_balance")
		# SQL is the boundary: reserved stock must not turn the actual-qty filter into a balance filter.
		with patch.object(frappe.db, "sql", return_value=[]) as sql:
			module.execute({"item": "Fabric", "warehouse": "S-001", "remove_zero_balance_item": 1})
		query, values = sql.call_args.args
		self.assertIn("b.actual_qty != 0", query)
		self.assertIn("b.actual_qty - b.reserved_qty", query)
		self.assertEqual(values, {"item": "Fabric", "warehouse": "S-001"})

	def test_conversion_pairs_by_position_and_retains_unmatched_side(self):
		module = report("item_conversion_report")
		conversions = [
			frappe._dict(
				item_conversion="IC-1",
				posting_date="2026-09-01",
				location="S-1",
				location_name="Store",
				from_item="Old",
				to_item="New",
			)
		]
		details = [
			frappe._dict(parent="IC-1", parentfield="from_items", item_variant="Old-M", lot="L-1", qty=5),
			frappe._dict(parent="IC-1", parentfield="from_items", item_variant="Old-L", lot="L-2", qty=3),
			frappe._dict(parent="IC-1", parentfield="to_items", item_variant="New-M", lot="L-1", qty=8),
		]
		with patch.object(frappe.db, "sql", side_effect=[conversions, details]):
			rows = module.execute({})[1]
		self.assertEqual([(r["from_qty"], r["to_qty"]) for r in rows], [(5, 8), (3, None)])
		with patch.object(frappe.db, "sql", side_effect=[conversions, details]):
			rows = module.execute({"lot": "L-2"})[1]
		self.assertEqual([(r["from_item_variant"], r["to_item_variant"]) for r in rows], [("Old-L", None)])

	def test_conversion_rejects_reversed_dates(self):
		module = report("item_conversion_report")
		with patch.object(frappe, "throw", side_effect=ValueError), self.assertRaises(ValueError):
			module.execute({"from_date": "2026-10-01", "to_date": "2026-09-01"})

	def test_consumption_includes_nested_groups_without_siblings(self):
		module = report("lot_consumption_report")
		groups = [
			frappe._dict(name="All", parent_item_group="", is_group=1),
			frappe._dict(name="Fabric", parent_item_group="All", is_group=1),
			frappe._dict(name="Knits", parent_item_group="Fabric", is_group=1),
			frappe._dict(name="Jersey", parent_item_group="Knits", is_group=0),
			frappe._dict(name="Labels", parent_item_group="All", is_group=0),
		]
		with patch.object(frappe, "get_all", return_value=groups):
			self.assertCountEqual(module.get_item_groups("Fabric"), ["Fabric", "Knits", "Jersey"])
			self.assertEqual(module.get_item_groups("Labels"), ["Labels"])

	def ledger(self, qty, date, rate, **kwargs):
		return frappe._dict(
			name="Fabric-M",
			item_name="Fabric",
			item_group="Fabric",
			brand=None,
			stock_uom="Kg",
			lot="L-1",
			warehouse="S-1",
			qty=qty,
			posting_date=date,
			rate=rate,
			valuation_rate=rate,
			voucher_type="YRP Stock Entry",
			voucher_no="STE-1",
			qty_after_transaction=qty,
			**kwargs,
		)

	def test_ageing_fifo_depletes_oldest_stock_and_splits_remaining_rates(self):
		module = report("lot_wise_stock_ageing")
		filters = frappe._dict(range1=30, range2=60, range3=90, show_warehouse_wise_stock=0)
		entries = [
			self.ledger(10, "2026-01-01", 2),
			self.ledger(8, "2026-09-01", 4),
			self.ledger(-6, "2026-09-02", 0),
		]
		details = module.FIFOSlots(filters, entries).generate()
		with patch.object(frappe.db, "get_single_value", return_value=3):
			rows = module.format_report_data(filters, details, "2026-09-30")
		self.assertEqual(
			(rows[0]["qty"], rows[0]["total_value"], rows[0]["range1"], rows[0]["range4"]), (12, 40, 8, 4)
		)
		self.assertEqual([(r["qty"], r["rate"]) for r in rows[1:]], [(4, 2), (8, 4)])

	def test_ageing_reconciliation_uses_balance_delta(self):
		module = report("lot_wise_stock_ageing")
		filters = frappe._dict(show_warehouse_wise_stock=1)
		reconcile = self.ledger(99, "2026-02-01", 3)
		reconcile.update(voucher_type="YRP Stock Reconciliation", qty_after_transaction=7)
		details = module.FIFOSlots(filters, [self.ledger(10, "2026-01-01", 2), reconcile]).generate()
		self.assertEqual(details[("Fabric-M", "S-1", "L-1")]["total_qty"], 7)

	def test_ageing_bucket_boundaries(self):
		module = report("lot_wise_stock_ageing")
		filters = frappe._dict(range1=30, range2=60, range3=90)
		slots = [[1, "2026-09-01", 2], [2, "2026-08-02", 2], [3, "2026-07-03", 2], [4, "2026-07-02", 2]]
		self.assertEqual(module.get_range_age(filters, slots, "2026-10-01", {}), (1, 2, 3, 4))


class TestStockASnapshotReports(TestCase):
	"""Read-only regression cases from the supplied migration snapshot."""

	def setUp(self):
		if not frappe.db.exists("SD YRP Lot", "C0925-57/1") or not frappe.db.exists(
			"SD YRP Lot", "JB2627-015"
		):
			self.skipTest("Requires the supplied MRP migration snapshot.")

	def test_ageing_reads_migrated_item_variants(self):
		module = report("lot_wise_stock_ageing")
		filters = frappe._dict(
			to_date="2026-09-30", lot="__stock_a_missing_lot__", range1=30, range2=60, range3=90
		)
		self.assertEqual(module.execute(filters)[1], [])

	def test_balance_includes_flat_migrated_variants(self):
		module = report("item_balance")
		rows = module.execute(
			{
				"lot": "C0925-57/1",
				"item": "Printed Bopp Junior Small-Pink (65 Mic)",
				"remove_zero_balance_item": 1,
			}
		)[1]
		self.assertTrue(rows)
		self.assertEqual(rows[0]["item"], "Printed Bopp Junior Small-Pink (65 Mic)")

	def test_consumption_uses_earliest_voucher_bucket_representative(self):
		module = report("lot_consumption_report")
		rows = module.execute(
			{
				"lot": "JB2627-015",
				"start_date": "2026-08-01",
				"end_date": "2026-09-30",
				"item_group": "Products",
			}
		)[1]
		row = next(
			row
			for row in rows
			if row.item_variant
			== "535473 - LADIES CREAM XMAS DOGS AOP B-12-14-White Cream Dogs AOP-Front Placket Left"
			and row.valuation_rate == 8.572
		)
		self.assertEqual(
			(row.stock_ledger_entry, row.from_warehouse, row.voucher_no),
			("SLE-2026-675441", "S-0170", "DC-2627-04327"),
		)
		self.assertEqual(row.quantity, -600)

	def test_ageing_includes_flat_migrated_variants(self):
		module = report("lot_wise_stock_ageing")
		filters = frappe._dict(
			lot="C0925-57/1", item="Printed Bopp Junior Small-Pink (65 Mic)", to_date="2026-09-30"
		)
		self.assertTrue(module.FIFOSlots(filters).generate())
