"""Regressions for the assigned stock and Sewing SCR parity fixes."""

from importlib import import_module
from unittest import TestCase
from unittest.mock import patch

import frappe


def report(slug):
	return import_module(f"essdee_yrp.essdee_yrp.report.sd_yrp_{slug}.sd_yrp_{slug}")


class TestStockParity(TestCase):
	def test_consumption_expands_copied_groups_without_including_siblings(self):
		groups = [
			frappe._dict(name=name, parent_item_group=parent, is_group=is_group)
			for name, parent, is_group in [
				("All", "", 1),
				("Purchase", "All", 1),
				("Accessories", "Purchase", 1),
				("Labels", "Accessories", 0),
				("Products", "All", 0),
				("M_Purchase", "All", 1),
				("M_Accessories", "M_Purchase", 1),
				("M_Labels", "M_Accessories", 0),
				("M_Products", "All", 0),
			]
		]
		with patch.object(frappe, "get_all", return_value=groups):
			self.assertCountEqual(
				report("lot_consumption_report").get_item_groups("Purchase"),
				["Purchase", "Accessories", "Labels", "M_Purchase", "M_Accessories", "M_Labels"],
			)
			self.assertCountEqual(
				report("lot_consumption_report").get_item_groups("M_Labels"), ["Labels", "M_Labels"]
			)

	def test_ageing_keeps_three_decimals_and_legacy_half_ties(self):
		module = report("lot_wise_stock_ageing")
		details = frappe._dict(
			name="Fabric-M", item_name="Fabric", item_group="Fabric", brand=None, lot="L-1", stock_uom="Kg"
		)
		filters = frappe._dict(range1=30, range2=60, range3=90)
		# Source settings are precision 3 / legacy rounding. Target settings are
		# precision 2 / modern banker's rounding; neither may alter this report.
		with (
			patch.object(frappe.db, "get_single_value", return_value="2"),
			patch.object(frappe, "get_system_settings", return_value="Banker's Rounding"),
		):
			rows = module.format_report_data(
				filters,
				{"item": dict(details=details, total_qty=1, fifo_queue=[[1, "2026-09-01", 1.2345]])},
				"2026-09-30",
			)
		self.assertEqual(rows[0]["total_value"], 1.235)
		self.assertEqual(rows[0]["rate"], 1.235)
		self.assertEqual(rows[1]["total_value"], 1.235)

	def test_consumption_snapshot_restores_accessories(self):
		if not frappe.db.exists("SD YRP Lot", "C0925-57/1"):
			self.skipTest("Requires migrated snapshot")
		rows = report("lot_consumption_report").execute(
			dict(lot="C0925-57/1", start_date="2026-08-01", end_date="2026-09-30", item_group="Purchase")
		)[1]
		self.assertEqual(len(rows), 27)
		label = next(r for r in rows if r.item_variant == "Flag Woven Label-ESSDEE-Black")
		self.assertEqual((label.quantity, label.item_group), (-3787, "Purchase Accessories"))
		box = next(r for r in rows if r.item_variant == "Bottom Box 310mm X 215mm X65mm")
		self.assertEqual((box.item_group, box.quantity), ("Purchase Accessories", -5990))

	def test_ageing_snapshot_displays_source_group_and_fractional_value(self):
		if not frappe.db.exists("SD YRP Lot", "C0925-57/1"):
			self.skipTest("Requires migrated snapshot")
		rows = report("lot_wise_stock_ageing").execute(
			dict(lot="C0925-57/1", to_date="2026-09-30", range1=30, range2=60, range3=90)
		)[1]
		box = next(r for r in rows if r["item"] == "Bottom Box 310mm X 215mm X65mm")
		self.assertEqual(box["item_group"], "Purchase Accessories")
		self.assertEqual((rows[0]["rate"], rows[0]["total_value"]), (6.009, 70.308))
		self.assertEqual(len(rows), 706)
