"""Regression checks for migrated stock and merch Desk reports."""

import importlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import frappe


def report(slug):
	try:
		return importlib.import_module(f"essdee_yrp.essdee_yrp.report.sd_yrp_{slug}.sd_yrp_{slug}")
	except ModuleNotFoundError:
		return None


class TestStockMerchDeskReports(unittest.TestCase):
	def setUp(self):
		translation = patch("frappe.translate.get_all_translations", return_value={})
		translation.start()
		self.addCleanup(translation.stop)

	def test_stock_ledger_signed_quantities_and_legacy_rate(self):
		module = report("stock_ledger")
		self.assertIsNotNone(module, "Stock Ledger port is missing")
		rows = [frappe._dict(qty=5, rate=12), frappe._dict(qty=-3, rate=12)]
		with patch.object(module, "get_data", return_value=rows):
			columns, actual = module.execute({"from_date": "2026-09-01", "to_date": "2026-09-21"})
		self.assertEqual([(r.in_qty, r.out_qty) for r in actual], [(5, 0), (0, -3)])
		self.assertTrue(all("in_out_rate" not in r for r in actual))
		self.assertEqual([c["fieldname"] for c in columns].count("voucher_no"), 2)

	def test_reservation_rejects_missing_and_reversed_dates(self):
		module = report("reserved_stock")
		self.assertIsNotNone(module, "Reserved Stock port is missing")
		for filters in (
			{},
			{"from_date": "2026-09-21"},
			{"from_date": "2026-09-21", "to_date": "2026-09-01"},
		):
			with (
				self.subTest(filters=filters),
				patch.object(module.frappe, "throw", side_effect=ValueError),
				self.assertRaises(ValueError),
			):
				module.execute(filters)

	def test_reservation_omitted_brand_keeps_source_null_equality_empty_result(self):
		module = report("reserved_stock")
		with patch.object(frappe, "db", new=MagicMock()) as database:
			database.sql.return_value = [frappe._dict(voucher_qty=7)]
			_columns, rows = module.execute({"from_date": "2026-09-01", "to_date": "2026-09-21"})
		self.assertEqual(rows, [])

	def test_reservation_explicit_empty_brand_queries_unbranded_items(self):
		module = report("reserved_stock")
		with patch.object(frappe, "db", new=MagicMock()) as database:
			database.sql.return_value = [frappe._dict(voucher_qty=7)]
			_columns, rows = module.execute(
				{
					"from_date": "2026-09-01",
					"to_date": "2026-09-21",
					"brand": "",
				}
			)
			query, values = database.sql.call_args.args
		self.assertEqual(rows, [{"voucher_qty": 7}])
		self.assertIn("i.brand = %(brand)s", query)
		self.assertEqual(values["brand"], "")

	def test_profit_interleaves_revisions_without_overwriting_newest(self):
		module = report("lot_profit_comparison")
		self.assertIsNotNone(module, "Lot Profit Comparison port is missing")
		entries = [
			frappe._dict(
				name=name,
				item="A",
				lot="L",
				lot_costing_type=kind,
				total_qty=qty,
				profit_percent_markdown=qty,
			)
			for name, kind, qty in [
				("new", "Final Qty", 9),
				("older", "Final Qty", 8),
				("plan", "Planned Qty", 12),
				("cost", "Costing", 14),
			]
		]
		rows = module.combine_revisions(entries)
		self.assertEqual(len(rows), 2)
		self.assertEqual(
			(rows[0]["Final Qty_qty"], rows[0]["Planned Qty_qty"], rows[0]["Costing_qty"]), (9, 12, 14)
		)
		self.assertEqual(rows[1]["Final Qty_name"], "older")

	def test_fg_placeholder_lot_scans_forward_and_preserves_last(self):
		module = report("fg_stock_with_lot")
		self.assertIsNotNone(module, "FG Stock With Lot port is missing")
		rows = [{"lot": "FG"}, {"lot": "Not Applicable"}, {"lot": "L1"}, {"lot": None}]
		self.assertEqual(module.get_next_non_fg_lot("FG", rows, 0), "L1")
		self.assertIsNone(module.get_next_non_fg_lot("FG", rows, 3))

	def test_fg_duplicate_lots_sum_values_and_keep_first_date(self):
		module = report("fg_stock_with_lot")
		self.assertIsNotNone(module, "FG Stock With Lot port is missing")
		rows = [
			{
				"item": "A",
				"lot": "L",
				"qty": 2,
				"stock_in_pcs": 20,
				"stock_price": 100,
				"entry_date": "2026-09-21",
			},
			{
				"item": "A",
				"lot": "L",
				"qty": 3,
				"stock_in_pcs": 30,
				"stock_price": 150,
				"entry_date": "2026-09-20",
			},
		]
		actual = module.duplicate_removed_data(rows)
		self.assertEqual(len(actual), 1)
		self.assertEqual(
			(actual[0]["qty"], actual[0]["stock_in_pcs"], actual[0]["stock_price"], actual[0]["entry_date"]),
			(5, 50, 250, "2026-09-21"),
		)

	def test_fg_allocation_clips_newest_entries_to_remaining_stock(self):
		module = report("fg_stock_with_lot")
		stock = {"A-M": {"stock": 5, "price": 100, "conversion_factor": 10}}
		entries = [
			{
				"item_variant": "A-M",
				"item": "A",
				"qty": qty,
				"lot": lot,
				"warehouse": "S",
				"warehouse_name": "Store",
				"pcs_per_box": 10,
				"entry_date": date,
			}
			for qty, lot, date in [(3, "FG", "2026-09-21"), (4, "L", "2026-09-20"), (8, "OLD", "2026-09-19")]
		]
		self.assertTrue(hasattr(module, "allocate_fg_entries"), "FG allocation helper is missing")
		rows = module.allocate_fg_entries(entries, stock, "FG")
		self.assertEqual([(row["lot"], row["qty"]) for row in rows], [("L", 3), ("L", 2)])
		self.assertEqual(sum(row["stock_in_pcs"] for row in rows), 50)
		self.assertEqual(sum(row["stock_price"] for row in rows), 500)

	def test_item_selectors_distinguish_parents_and_variants(self):
		script = """
		const fs = require('fs');
		const vm = require('vm');
		const context = {
			__: value => value,
			frappe: {
				query_reports: {},
				datetime: {get_today: () => '2026-09-21', add_months: () => '2026-08-21'},
				query_report: {get_filter_value: () => process.argv[2] || null},
			},
		};
		vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), context);
		const report = Object.values(context.frappe.query_reports)[0];
		process.stdout.write(JSON.stringify(Object.fromEntries(
			report.filters.filter(f => f.get_query).map(f => [f.fieldname, f.get_query().filters])
		)));
		"""
		root = Path(__file__).parent / "essdee_yrp" / "report"
		queries = []
		for slug, parent in [
			("stock_ledger", ""),
			("reserved_stock", ""),
			("reserved_stock", "ESSDEE GYM VEST"),
		]:
			path = root / f"sd_yrp_{slug}" / f"sd_yrp_{slug}.js"
			queries.append(json.loads(subprocess.check_output(["node", "-e", script, str(path), parent])))
		self.assertEqual(queries[0].get("parent_item", {}).get("variant_of"), ["is", "not set"])
		self.assertEqual(queries[0]["item"]["variant_of"], ["is", "set"])
		self.assertEqual(queries[1]["item"].get("variant_of"), ["is", "not set"])
		self.assertEqual(queries[1]["item_code"]["variant_of"], ["is", "set"])
		self.assertEqual(queries[2]["item_code"]["variant_of"], "ESSDEE GYM VEST")

	def test_workspace_links_are_in_matching_owned_workspaces(self):
		root = Path(__file__).parent
		for path, names in [
			(
				root / "essdee_yrp/workspace/stock_reports/stock_reports.json",
				["SD YRP Stock Ledger", "SD YRP Reserved Stock"],
			),
			(root / "essdee_yrp/workspace/finishing/finishing.json", ["SD YRP FG Stock With Lot"]),
			(root / "essdee_yrp/workspace/merch/merch.json", ["SD YRP Lot Profit Comparison"]),
		]:
			workspace = json.loads(path.read_text())
			links = {row.get("link_to") for row in workspace["links"] if row.get("link_type") == "Report"}
			self.assertTrue(set(names) <= links)

	def test_report_metadata_uses_migrated_doctypes_and_source_roles(self):
		root = Path(__file__).parent / "essdee_yrp" / "report"
		for slug, name, ref, roles in [
			(
				"stock_ledger",
				"Stock Ledger",
				"YRP Stock Ledger Entry",
				{"Stock User", "Accounts Manager", "Stock Manager", "Merch Manager", "Merch User"},
			),
			(
				"reserved_stock",
				"Reserved Stock",
				"YRP Stock Reservation Entry",
				{"System Manager", "Merch Manager", "Merch User"},
			),
			(
				"fg_stock_with_lot",
				"FG Stock With Lot",
				"SD YRP FG Stock Entry",
				{"System Manager", "Accounts User", "Accounts Manager"},
			),
			(
				"lot_profit_comparison",
				"Lot Profit Comparison",
				"SD YRP Lotwise Item Profit",
				{"System Manager", "PD Manager", "PD User"},
			),
		]:
			path = root / f"sd_yrp_{slug}" / f"sd_yrp_{slug}.json"
			with self.subTest(report=name):
				self.assertTrue(path.exists(), f"Missing metadata: {name}")
				metadata = json.loads(path.read_text())
				self.assertEqual(
					(metadata["name"], metadata["ref_doctype"], metadata["module"], metadata["report_type"]),
					(f"SD YRP {name}", ref, "Essdee YRP", "Script Report"),
				)
				self.assertEqual({r["role"] for r in metadata["roles"]}, roles)
