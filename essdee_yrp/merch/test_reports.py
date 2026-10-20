import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.merch import reports

PROCESSES = ["Yolk Fusing", "Chest Fusing", "Printing", "Ironing"]
LIVE_LOTS = ["C0826-54", "C0826-57", "C0426-35/2"]


def reference_lot_filters(test, category):
	names = json.loads(Path(__file__).with_name(f"test_reports_{category}_lots.json").read_text())
	existing = frappe.db.get_all("SD YRP Lot", filters={"name": ["in", names]}, pluck="name")
	if set(names) - set(existing):
		test.skipTest(f"Reference {category} lots are absent")
	return {"lot": names, "lot_status": "Open", "process_list": PROCESSES}


def fixture_sources():
	return {
		"details": [{"name": "IPD", "cutting_process": "Cutting", "stiching_process": "Stitching",
			"stiching_in_stage": "Cut", "packing_combo": 6, "part_qty": 1}],
		"orders": [fixture_order("CUT", "Cutting", 110, 100), fixture_order("SEW", "Combined Stitching", 90, 80),
			fixture_order("FUSE", "Yolk Fusing", 100, 98), fixture_order("PRINT", "Printing", 98, 95),
			fixture_order("IRON", "Ironing and Packing", 60, 58)],
		"receipts": [{"against_id": "SEW", "accepted": 75, "version": 0}],
		"stages": [{"parent": "IPD", "process_name": name, "in_stage": stage}
			for name, stage in (("Yolk Fusing", "Cut"), ("Printing", "Cut"), ("Ironing", "Piece"))],
		"expansions": [{"parent": "Combined Stitching", "process_name": "Stitching"},
			{"parent": "Ironing and Packing", "process_name": "Ironing"}],
		"quantities": [{"parent": "LOT", "quantity": 110}], "reworks": [{"lot": "LOT", "quantity": 3}],
		"plans": [{"name": "PLAN", "lot": "LOT", "work_order": "PACK", "pieces_per_box": 5,
			"dispatched": 2, "inward": 60, "transferred": 2}],
	}


def fixture_order(name, process, sent, received, **values):
	return {"name": name, "lot": "LOT", "process_name": process, "sent": sent, "received": received,
		"is_rework": 0, "includes_packing": 0, "first_dc_date": "2026-09-01", "last_grn_date": "2026-09-20", **values}


def fixture_row(sources):
	return reports.build_row({"name": "LOT", "item": "STYLE", "production_order": "PPO", "production_detail": "IPD"},
		reports.lot_context(sources), PROCESSES)


class TestWorkInProgress(TestCase):
	def test_registration_is_callable_and_isolated_from_planning(self):
		from essdee_yrp.web_reports import get_reports

		with patch.object(frappe.db, "get_single_value", return_value="Accepted"):
			entries = {entry.key: entry for entry in get_reports()}
		entry = entries["merch-work-in-progress"]
		self.assertEqual(entry.kind, "callable")
		self.assertEqual(entry.runner, "essdee_yrp.merch.reports.run_work_in_progress")
		self.assertEqual(entry.access, "essdee_yrp.merch.reports.require_work_in_progress_access")
		self.assertEqual(entry.background, "never")
		self.assertEqual(entry.permission_doctypes, ("SD YRP Lot", "YRP Work Order"))
		self.assertEqual(entry.filters["product_season"], ("Link", "SD YRP Product Season"))
		self.assertEqual(entry.link_sources["production_order"], "YRP Production Order")
		self.assertEqual(entries["planning-work-in-progress"].runner, "essdee_yrp.planning.reports.work_in_progress.run")

	def test_filter_rule_and_date_pair(self):
		for filters, message in (({}, "Set at least one filter"), ({"lot": ["LOT"], "from_date": "2026-10-15"}, "To Date"),
			({"lot": ["LOT"], "to_date": "2026-10-15"}, "From Date"),
			({"item": ["STYLE"], "lot_status": ""}, "Lot Status"),
			({"category": "Vest", "from_date": "2026-10-16", "to_date": "2026-10-15"}, "on or after")):
			with self.subTest(filters=filters), self.assertRaisesRegex(frappe.ValidationError, message):
				reports.validate_filters(filters)
		for key, value in (("category", "Vest"), ("product_season", "Winter"), ("lot", ["LOT"]), ("item", ["STYLE"])):
			self.assertEqual(reports.validate_filters({key: value})["lot_status"], "Open")

	def test_process_filters_accept_both_ordered_shapes(self):
		self.assertEqual(reports.filter_names('["Ironing", "Cutting", "Ironing"]', processes=True), ["Ironing", "Cutting"])
		self.assertEqual(reports.filter_names([{"process_name": "Ironing"}], processes=True), ["Ironing"])
		for value in ({}, [1], [""], [None]):
			with self.assertRaises(frappe.ValidationError):
				reports.filter_names(value)

	@patch.object(reports.frappe, "get_list")
	def test_lot_resolution_is_permission_aware_and_to_date_midnight_inclusive(self, get_list):
		get_list.side_effect = [["LOT"], [{"name": "LOT", "creation": "2026-10-15 23:59:59"}]]
		filters = reports.validate_filters({"lot": ["LOT"], "from_date": "2026-10-15", "to_date": "2026-10-15"})
		self.assertEqual(reports.resolve_lots(filters)[0]["name"], "LOT")
		conditions = get_list.call_args.kwargs["filters"]
		self.assertIn(["creation", ">=", "2026-10-15"], conditions)
		self.assertIn(["creation", "<=", "2026-10-15"], conditions)
		self.assertEqual(get_list.call_args.args, ("SD YRP Lot",))

	@patch.object(reports.frappe, "get_list")
	def test_category_and_season_are_applied_together(self, get_list):
		get_list.side_effect = [["Vest"], ["Winter"], ["STYLE"], []]
		reports.resolve_lots(reports.validate_filters({"category": "Vest", "product_season": "Winter"}))
		self.assertIn(["item", "in", ["STYLE"]], get_list.call_args.kwargs["filters"])
		self.assertIn(["season", "=", "Winter"], get_list.call_args.kwargs["filters"])

	def test_finishing_plan_formulas_and_combined_processes(self):
		row = fixture_row(fixture_sources())
		expected = {"order_qty": 110, "cut_qty": 100, "order_to_cut_diff": -10, "sewing_sent": 90,
			"sewing_received": 80, "cut_to_sew_diff": -10, "ready_for_packing": 68, "finishing_inward": 60,
			"in_sew": -10, "dispatch": 10, "in_packing": -50, "transferred": 2, "cut_to_dispatch_diff": -88,
			"cut_0_sent": 100, "cut_0_received": 98, "cut_0_diff": -2, "cut_0_to_cut_diff": -2,
			"cut_2_sent": 98, "cut_2_received": 95, "cut_2_diff": -3, "cut_2_to_yolk_fusing_diff": -3,
			"piece_3_sent": 60, "piece_3_received": 58, "piece_3_diff": -2, "piece_3_to_sew_diff": -2}
		self.assertEqual({key: row[key] for key in expected}, expected)
		self.assertEqual(row["not_in_ipd"], ["Chest Fusing"])
		self.assertNotIn("cut_1_sent", row)
		self.assertEqual(row["process_chains"]["cut_2"], "Yolk Fusing")
		self.assertEqual(row["process_chains"]["piece_3"], "Sew")
		self.assertEqual([row[key] for key, label in reports.DATES], ["2026-09-20", "2026-09-01", "2026-09-20"])

	def test_no_plan_and_no_packing_keeps_sewing_inward(self):
		sources = fixture_sources()
		sources["plans"] = []
		row = fixture_row(sources)
		self.assertEqual((row["finishing_inward"], row["dispatch"], row["ready_for_packing"]), (80, 0, 78))
		self.assertEqual((row["in_packing"], row["cut_to_dispatch_diff"]), (-80, -100))

	def test_set_item_includes_packing_dynamic_and_legacy(self):
		for version, expected in ((2, 6), (0, 36)):
			with self.subTest(version=version):
				sources = fixture_sources()
				sources["plans"] = []
				sources["details"][0]["part_qty"] = 2
				sources["orders"][1].update(includes_packing=1, received=3)
				sources["receipts"] = [{"against_id": "SEW", "version": version, "accepted": 3,
					"dynamic_pieces": 3 if version == 2 else 0, "legacy_boxes": 3 if version == 0 else 0, "stock_qty": 35}]
				row = fixture_row(sources)
				self.assertEqual(row["sewing_received"], expected)
				self.assertEqual(row["dispatch"], expected)
				self.assertEqual(row["finishing_inward"], 35)
				self.assertEqual(row["ready_for_packing"], 6)

	def test_batch_tracked_plan_and_empty_children(self):
		sources = fixture_sources()
		sources["details"][0]["part_qty"] = 2
		sources["receipts"].append({"against_id": "PACK", "version": 1})
		self.assertEqual(fixture_row(sources)["dispatch"], 4)
		sources["plans"][0].update(dispatched=None, inward=None, transferred=None)
		row = fixture_row(sources)
		self.assertEqual((row["dispatch"], row["transferred"], row["finishing_inward"]), (0, 0, 0))
		sources["plans"][0]["dispatched"] = 10000
		self.assertEqual(fixture_row(sources)["ready_for_packing"], 0)

	def test_in_ipd_without_work_order_has_zeroes_and_no_chain(self):
		sources = fixture_sources()
		sources["orders"] = [row for row in sources["orders"] if row["name"] != "IRON"]
		row = fixture_row(sources)
		self.assertEqual([row[f"piece_3_{key}"] for key in ("sent", "received", "diff")], [0, 0, 0])
		self.assertNotIn("piece_3_to_sew_diff", row)
		self.assertNotIn("Ironing", row["not_in_ipd"])
		result = reports.build_result([row], PROCESSES)
		self.assertFalse(any(col["fieldname"].startswith("piece_3_to_") for col in result["columns"]))

	def test_no_work_order_does_not_advance_cut_or_piece_chain(self):
		sources = fixture_sources()
		sources["orders"] = [row for row in sources["orders"] if row["name"] != "FUSE"]
		sources["stages"].append({"parent": "IPD", "process_name": "Chest Fusing", "in_stage": "Piece"})
		row = fixture_row(sources)
		self.assertNotIn("cut_0_to_cut_diff", row)
		self.assertNotIn("piece_1_to_sew_diff", row)
		self.assertEqual(row["process_chains"]["cut_2"], "Cut")
		self.assertEqual(row["process_chains"]["piece_3"], "Sew")

	def test_cut_dates_use_exact_process_and_quantities_exclude_rework(self):
		sources = fixture_sources()
		sources["expansions"].append({"parent": "Combined Cutting", "process_name": "Cutting"})
		sources["orders"].extend([
			fixture_order("COMBINED-CUT", "Combined Cutting", 5, 5, last_grn_date="2026-10-15"),
			fixture_order("REWORK-CUT", "Cutting", 10, 10, is_rework=1, last_grn_date="2026-10-01"),
		])
		row = fixture_row(sources)
		self.assertEqual(row["cut_qty"], 105)
		self.assertEqual(row["last_cut_date"], "2026-10-01")

	def test_no_stitching_work_order_keeps_cut_only_row(self):
		sources = fixture_sources()
		sources["orders"] = [row for row in sources["orders"] if row["name"] != "SEW"]
		row = fixture_row(sources)
		self.assertEqual((row["cut_qty"], row["order_to_cut_diff"]), (100, -10))
		self.assertTrue(all(row[key] == 0 for key, label in (*reports.SEWING, *reports.FINISHING)))
		self.assertFalse(row["process_chains"])
		self.assertEqual((row["process_stages"], row["not_in_ipd"]), ({}, []))

	def test_cut_only_ipd_does_not_create_process_columns_or_summary_tiles(self):
		sources = fixture_sources()
		sources["stages"] = [stage for stage in sources["stages"] if stage["process_name"] != "Printing"]
		row = fixture_row(sources)
		sources = fixture_sources()
		sources["orders"] = [order for order in sources["orders"] if order["name"] != "SEW"]
		sources["stages"][0]["in_stage"] = "Piece"
		cut_only = fixture_row(sources)
		for rows in ([cut_only, row], [row, cut_only]):
			result = reports.build_result(rows, PROCESSES)
			self.assertFalse(any(col.get("process") == "Printing" for col in result["columns"]))
			self.assertFalse(any(col["fieldname"].startswith("piece_0_") for col in result["columns"]))
			self.assertNotIn("Printing Diff", result["summary"])
			self.assertFalse(any(tile["label"].startswith("Printing") for tile in result["report_summary"]))
			self.assertEqual(result["not_in_ipd_processes"], ["Chest Fusing", "Printing"])
			self.assertTrue(all(col["fieldname"] not in cut_only for col in result["columns"] if col.get("process")))
		self.assertFalse(any(col.get("process") for col in reports.build_result([cut_only], PROCESSES)["columns"]))

	def test_columns_separate_stages_and_each_chain_predecessor(self):
		row = fixture_row(fixture_sources())
		sources = fixture_sources()
		sources["stages"][0]["in_stage"] = "Piece"
		other = fixture_row(sources)
		other["lot"] = "OTHER"
		result = reports.build_result([row, other], PROCESSES)
		columns = {col["fieldname"]: col for col in result["columns"]}
		self.assertEqual(columns["cut_0_diff"]["group"], "Yolk Fusing (cut stage)")
		self.assertEqual(columns["piece_0_diff"]["group"], "Yolk Fusing (piece stage)")
		self.assertEqual(columns["piece_3_to_sew_diff"]["label"], "Ironing to Sew Diff")
		self.assertEqual(columns["piece_3_to_yolk_fusing_diff"]["label"], "Ironing to Yolk Fusing Diff")
		self.assertNotIn("piece_0_diff", row)
		self.assertNotIn("cut_0_diff", other)
		self.assertNotIn("piece_3_to_yolk_fusing_diff", row)
		self.assertNotIn("piece_3_to_sew_diff", other)
		self.assertEqual(result["summary"], {"Lots": 2, "Order to Cut": -20, "Cut to Sew": -20,
			"In Sew": -20, "Ready for Packing": 136, "In Packing": -100, "Cut to Dispatch": -176,
			"Yolk Fusing Diff (cut stage)": -2, "Printing Diff": -6, "Printing to Yolk Fusing Diff": -3,
			"Yolk Fusing Diff (piece stage)": -2, "Ironing Diff": -4, "Ironing to Yolk Fusing Diff": -40})
		self.assertEqual(result["totals"]["piece_3_to_sew_diff"], -2)
		self.assertEqual(result["totals"]["piece_3_to_yolk_fusing_diff"], -40)
		self.assertEqual(result["not_in_ipd_processes"], ["Chest Fusing"])
		self.assertFalse(any(col.get("process") == "Chest Fusing" for col in columns.values()))
		self.assertEqual(list(dict.fromkeys(col["group"] for col in columns.values())),
			["", "Cut", "Yolk Fusing (cut stage)", "Printing", "Sewing", "Yolk Fusing (piece stage)",
				"Ironing", "Finishing", "Dates"])
		self.assertEqual([col["label"] for col in columns.values() if col["fieldname"].startswith("cut_2_")],
			["Printing Sent", "Printing Received", "Printing Diff", "Printing to Yolk Fusing Diff", "Printing to Cut Diff"])
		self.assertEqual(result["result"][-1]["style"], "Total")
		self.assertTrue(result["result"][-1]["is_total_row"])

	def test_missing_process_cells_do_not_contribute_to_totals(self):
		row = fixture_row(fixture_sources())
		sources = fixture_sources()
		sources["stages"] = [stage for stage in sources["stages"] if stage["process_name"] != "Printing"]
		other = fixture_row(sources)
		result = reports.build_result([row, other], PROCESSES)
		self.assertIn("Printing", other["not_in_ipd"])
		self.assertNotIn("cut_2_sent", other)
		self.assertEqual(result["totals"]["cut_2_sent"], 98)
		self.assertEqual(result["totals"]["cut_2_diff"], -3)
		self.assertEqual(result["summary"]["Printing Diff"], -3)
		self.assertEqual(result["not_in_ipd_processes"], ["Chest Fusing"])

	def test_totals_are_column_sums_with_cut_only_lot_in_any_position(self):
		row = fixture_row(fixture_sources())
		sources = fixture_sources()
		sources["orders"] = [order for order in sources["orders"] if order["name"] != "SEW"]
		cut_only = fixture_row(sources)
		for rows in ([cut_only, row], [row, cut_only]):
			result = reports.build_result(rows, PROCESSES)
			self.assertEqual(result["totals"], {key: sum(row.get(key, 0) for row in rows)
				for key in result["totals"]})
			self.assertEqual(result["totals"]["cut_to_sew_diff"], -10)
			self.assertEqual(result["totals"]["cut_to_dispatch_diff"], -88)
			self.assertEqual(result["result"][-1], {"style": "Total", "is_total_row": True, **result["totals"]})

	@patch.object(reports.frappe, "has_permission", return_value=False)
	def test_access_denied_without_lot_read(self, permission):
		with self.assertRaises(frappe.PermissionError):
			reports.run_work_in_progress({"lot": ["LOT"]})

	@patch.object(reports.frappe, "has_permission")
	def test_both_lot_and_work_order_read_are_required(self, permission):
		for missing in ("SD YRP Lot", "YRP Work Order"):
			permission.side_effect = lambda doctype, **options: doctype != missing
			self.assertFalse(reports.can_view_work_in_progress())

	@patch.object(reports.frappe.db, "get_all", return_value=["HIDDEN"])
	@patch.object(reports.frappe, "get_list", return_value=[])
	def test_unreadable_filter_lot_is_rejected(self, get_list, get_all):
		with self.assertRaises(frappe.PermissionError):
			reports.resolve_lots(reports.validate_filters({"lot": ["HIDDEN"]}))

	@patch.object(reports.frappe.db, "get_all", return_value=["HIDDEN"])
	@patch.object(reports.frappe, "get_list", return_value=[])
	def test_unknown_pasted_names_are_validation_errors_before_unreadable_names(self, get_list, get_all):
		with self.assertRaisesRegex(frappe.ValidationError, "Unknown Lot: TYPO, MISSING"):
			reports.authorize_names("SD YRP Lot", ["TYPO", "HIDDEN", "MISSING"])
		get_all.assert_called_once_with("SD YRP Lot",
			filters={"name": ["in", ["TYPO", "HIDDEN", "MISSING"]]}, pluck="name")

	def test_query_count_is_bounded_for_three_and_fifty_lots(self):
		for count in (3, 50):
			with self.subTest(count=count):
				self.assert_batched_queries(count)

	def test_unreadable_work_orders_reject_all_selected_lots_before_loading(self):
		lots = [{"name": name, "production_detail": "IPD"} for name in ("LOT-1", "LOT-2")]
		with patch.object(reports.frappe, "get_list", return_value=[{"count": 1}]) as get_list, \
			patch.object(reports, "source_rows", return_value=[{"count": 2}]) as total, \
			patch.object(reports, "load_orders") as orders, patch.object(reports, "load_receipts") as receipts:
			with self.assertRaisesRegex(frappe.PermissionError, "You cannot read all Work Orders of the selected Lots"):
				reports.load_sources(lots)
		get_list.assert_called_once_with("YRP Work Order",
			filters={"lot": ["in", ("LOT-1", "LOT-2")], "docstatus": 1},
			fields=[{"COUNT": "*", "as": "count"}], order_by=None, limit_page_length=0)
		total.assert_called_once()
		orders.assert_not_called()
		receipts.assert_not_called()

	def assert_batched_queries(self, count):
		sources = fixture_sources()
		lots = [{"name": f"LOT-{index}", "item": "STYLE", "production_detail": "IPD"} for index in range(count)]
		for key in ("orders", "receipts", "quantities", "reworks", "plans"):
			sources[key] = [
				{field: (value.replace("LOT", lot["name"]) if isinstance(value, str) else value) for field, value in row.items()}
				for lot in lots for row in sources[key]
			]
		def query(sql, parameters=None, **options):
			self.assertTrue(sql.lstrip().upper().startswith("SELECT"), sql)
			if "COUNT(*) AS count FROM `tabYRP Work Order`" in sql:
				return [{"count": len(sources["orders"])}]
			if "tabSD YRP Finishing Plan Detail" in sql or "tabSD YRP Finishing Plan GRN Detail" in sql:
				return [{**row, "parent": row["name"]} for row in sources["plans"]]
			for table, key in (("tabYRP Item Production Detail", "details"), ("tabYRP Work Order Calculated Item", "orders"),
				("tabYRP Goods Received Note`", "receipts"), ("tabYRP IPD Process", "stages"), ("tabYRP Process Details", "expansions"),
				("tabSD YRP Lot Order Detail", "quantities"), ("tabSD YRP GRN Rework Item`", "reworks"),
				("tabSD YRP Finishing Plan`", "plans")):
				if table in sql:
					return sources[key]
			return []
		def get_list(doctype, **options):
			reports.frappe.db.sql("SELECT permission_aware_lots")
			if doctype == "YRP Work Order":
				return [{"count": len(sources["orders"])}]
			return [lot["name"] for lot in lots] if options.get("pluck") else lots
		def get_setting(*args):
			reports.frappe.db.sql("SELECT settings")
			return "Accepted"
		with patch.object(reports.frappe, "has_permission", return_value=True), patch.object(reports.frappe, "get_list", side_effect=get_list), \
			patch.object(reports.frappe.db, "get_single_value", side_effect=get_setting), \
			patch.object(reports.frappe.db, "sql", side_effect=query) as sql:
			result = reports.run_work_in_progress({"lot": [lot["name"] for lot in lots]})
			self.assertEqual(result["summary"]["Lots"], count)
			self.assertEqual(result["totals"]["cut_qty"], 100 * count)
			self.assertLessEqual(sql.call_count, 15)


class TestWorkInProgressLive(TestCase):
	def setUp(self):
		if not all(frappe.db.exists("SD YRP Lot", lot) for lot in LIVE_LOTS):
			self.skipTest("Live Merch parity lots are absent")
		self.previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, self.previous_user)

	def test_every_reference_cell_total_and_summary(self):
		result = reports.run_work_in_progress({"lot": LIVE_LOTS, "process_list": PROCESSES})
		rows = {row["lot"]: row for row in result["result"] if not row.get("is_total_row")}
		keys = [key for key, label in (*reports.CUT, *reports.SEWING, *reports.FINISHING)]
		expected = {
			"C0826-54": [12414, 12338, -76, 12338, 11473, 0, 10416, 1176, -865, 965, -211, 0, -11373],
			"C0826-57": [10152, 9862, -290, 9862, 2425, 0, 2418, 2425, -7437, 0, -2425, 0, -9862],
			"C0426-35/2": [18640, 18005, -635, 12818, 5118, -5187, 5015, 5118, -7700, 0, -5118, 0, -18005],
		}
		for lot, values in expected.items():
			self.assertEqual([rows[lot][key] for key in keys], values, lot)
		for index, key in enumerate(keys):
			self.assertEqual(result["totals"][key], sum(values[index] for values in expected.values()), key)
		self.assert_live_processes(rows, result)
		self.assert_live_dates(rows)
		self.assertEqual([col["label"] for col in result["columns"] if col.get("stage") == "cut"],
			["Yolk Fusing Sent", "Yolk Fusing Received", "Yolk Fusing Diff", "Yolk Fusing to Cut Diff",
				"Chest Fusing Sent", "Chest Fusing Received", "Chest Fusing Diff", "Chest Fusing to Yolk Fusing Diff",
				"Printing Sent", "Printing Received", "Printing Diff", "Printing to Yolk Fusing Diff"])
		self.assertEqual([col["label"] for col in result["columns"] if col.get("stage") == "piece"],
			["Ironing Sent", "Ironing Received", "Ironing Diff", "Ironing to Sew Diff"])
		self.assertEqual({key: result["summary"][key] for key in ("Lots", *(label for key, label in reports.SUMMARY))},
			{"Lots": 3, "Order to Cut": -1001, "Cut to Sew": -5187, "In Sew": -16002,
				"Ready for Packing": 17849, "In Packing": -7754, "Cut to Dispatch": -39240})
		for row in rows.values():
			lot = frappe.db.get_value("SD YRP Lot", row["lot"], ["item", "production_order"], as_dict=True)
			self.assertEqual((row["style"], row["production_order"]), (lot.item, lot.production_order or ""))

	def assert_live_processes(self, rows, result):
		values = {
			"C0826-54": [[12338, 12338, 0, 0], [12338, 12338, 0, 0], None, [1176, 1158, -18, -18]],
			"C0826-57": [[4931, 4931, 0, -4931], None, None, [0, 0, 0, None]],
			"C0426-35/2": [[18005, 18005, 0, 0], None, [18005, 18005, 0, 0], [0, 0, 0, None]],
		}
		for lot, groups in values.items():
			for index, group in enumerate(groups):
				if group is None:
					self.assertIn(PROCESSES[index], rows[lot]["not_in_ipd"])
					continue
				prefix = f"{'piece' if index == 3 else 'cut'}_{index}"
				keys = [f"{prefix}_{suffix}" for suffix in ("sent", "received", "diff")]
				keys.append(reports.chain_key(prefix, ("Cut", "Yolk Fusing", "Yolk Fusing", "Sew")[index]))
				self.assertEqual([rows[lot].get(key) for key in keys], group)
		for index in range(4):
			for position, suffix in enumerate(("sent", "received", "diff", "chain_diff")):
				prefix = f"{'piece' if index == 3 else 'cut'}_{index}"
				key = (reports.chain_key(prefix, ("Cut", "Yolk Fusing", "Yolk Fusing", "Sew")[index])
					if suffix == "chain_diff" else f"{prefix}_{suffix}")
				self.assertEqual(result["totals"][key],
					sum(group[index][position] or 0 for group in values.values() if group[index] is not None))
		self.assertEqual({key: value for key, value in result["summary"].items() if key.endswith(" Diff")},
			{"Yolk Fusing Diff": 0, "Chest Fusing Diff": 0, "Chest Fusing to Yolk Fusing Diff": 0,
				"Printing Diff": 0, "Printing to Yolk Fusing Diff": 0, "Ironing Diff": -18})

	def assert_live_dates(self, rows):
		for lot, dates in {
			"C0826-54": ["2026-08-25", "2026-09-05", "2026-09-19"],
			"C0826-57": ["2026-09-05", "2026-09-05", "2026-09-15"],
			"C0426-35/2": ["2026-08-21", "2026-08-19", "2026-09-08"],
		}.items():
			self.assertEqual([rows[lot][key] for key, label in reports.DATES], dates)

	def test_legacy_combined_stitching_reference(self):
		name = "C0625-39/3-256"
		if not frappe.db.exists("SD YRP Lot", name):
			self.skipTest("Legacy Merch parity lot is absent")
		result = reports.run_work_in_progress({"lot": [name], "process_list": ["Yolk Fusing"]})
		row = result["result"][0]
		keys = [key for key, label in (*reports.CUT, *reports.SEWING, *reports.FINISHING)]
		self.assertEqual([row[key] for key in keys], [1345, 1420, 75, 1420, 1401, 0, 131, 1372, -19, 1250, -122, 0, -170])
		self.assertEqual([result["totals"][key] for key in keys], [1345, 1420, 75, 1420, 1401, 0, 131, 1372, -19, 1250, -122, 0, -170])
		self.assertEqual([row[key] for key, label in reports.DATES], ["2025-09-17", "2025-09-22", "2025-10-10"])
		self.assertEqual(row["not_in_ipd"], ["Yolk Fusing"])
		self.assertEqual(result["totals"], {key: result["result"][-1][key] for key in result["totals"]})
		self.assertEqual([result["summary"][label] for key, label in reports.SUMMARY], [75, 0, -19, 131, -122, -170])

	def test_live_query_bound_and_read_only(self):
		filters = {"lot": LIVE_LOTS, "process_list": PROCESSES}
		reports.run_work_in_progress(filters)
		original_sql = frappe.db.sql
		pending_writes = frappe.db.transaction_writes
		def read_only_sql(query, *args, **kwargs):
			self.assertTrue(str(query).lstrip().upper().startswith("SELECT"), str(query))
			return original_sql(query, *args, **kwargs)
		with patch.object(frappe.db, "sql", side_effect=read_only_sql) as sql:
			reports.run_work_in_progress(filters)
			self.assertLessEqual(sql.call_count, 15)
		self.assertEqual(frappe.db.transaction_writes, pending_writes)

	def test_reference_lots_run_query_bound(self):
		filters = reference_lot_filters(self, "thermal")
		reports.run_work_in_progress(filters)
		with patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql:
			result = reports.run_work_in_progress(filters)
			self.assertGreaterEqual(result["summary"]["Lots"], 50)
			self.assertLessEqual(sql.call_count, 15)

	def test_real_creation_day_ends_at_midnight_like_mrp(self):
		created = str(frappe.db.get_value("SD YRP Lot", LIVE_LOTS[0], "creation"))[:10]
		result = reports.run_work_in_progress({"lot": [LIVE_LOTS[0]], "from_date": created, "to_date": created})
		self.assertEqual([row["lot"] for row in result["result"] if not row.get("is_total_row")], [])
		from frappe.utils import add_days
		result = reports.run_work_in_progress({"lot": [LIVE_LOTS[0]], "from_date": created, "to_date": str(add_days(created, 1))})
		self.assertEqual([row["lot"] for row in result["result"] if not row.get("is_total_row")], [LIVE_LOTS[0]])


class TestWorkInProgressThermal(TestCase):
	def test_thermal_stage_columns_and_chain_totals(self):
		filters = reference_lot_filters(self, "thermal")
		previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, previous_user)
		result = reports.run_work_in_progress(filters)
		self.assertEqual(result["summary"]["Lots"], 156)
		self.assertCountEqual([row["lot"] for row in result["result"] if not row.get("is_total_row")], filters["lot"])
		columns = result["columns"]
		for stage, expected in {
			"cut": ["Yolk Fusing Sent", "Yolk Fusing Received", "Yolk Fusing Diff", "Yolk Fusing to Cut Diff"],
			"piece": ["Yolk Fusing Sent", "Yolk Fusing Received", "Yolk Fusing Diff", "Yolk Fusing to Sew Diff",
				"Ironing Sent", "Ironing Received", "Ironing Diff", "Ironing to Sew Diff", "Ironing to Yolk Fusing Diff"],
		}.items():
			self.assertCountEqual([col["label"] for col in columns if col.get("stage") == stage], expected)
		self.assertEqual(result["totals"]["cut_0_diff"], 0)
		self.assertEqual(result["totals"]["piece_3_to_yolk_fusing_diff"], 2458)
		self.assertEqual(result["totals"]["piece_3_diff"], -193082)
		self.assertEqual(result["summary"]["Yolk Fusing Diff (cut stage)"], 0)
		self.assertEqual(result["summary"]["Yolk Fusing Diff (piece stage)"], 0)
		self.assertEqual(result["summary"]["Ironing Diff"], -193082)
		self.assertEqual(result["summary"]["Ironing to Yolk Fusing Diff"], 2458)
		self.assertEqual(result["not_in_ipd_processes"], ["Chest Fusing", "Printing"])
		self.assertFalse(any(col.get("process") in ("Chest Fusing", "Printing") for col in columns))


class TestWorkInProgressVest(TestCase):
	def test_reference_lots_have_no_printing_columns_and_exact_dynamic_summary(self):
		filters = reference_lot_filters(self, "vest")
		previous_user = frappe.session.user
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, previous_user)
		result = reports.run_work_in_progress(filters)
		self.assertEqual(result["summary"]["Lots"], 27)
		self.assertCountEqual([row["lot"] for row in result["result"] if not row.get("is_total_row")], filters["lot"])
		self.assertFalse(any(col.get("process") == "Printing" for col in result["columns"]))
		fixed = {"Lots", *(label for key, label in reports.SUMMARY)}
		self.assertEqual({key: value for key, value in result["summary"].items() if key not in fixed},
			{"Yolk Fusing Diff": 0, "Chest Fusing Diff": 0, "Chest Fusing to Yolk Fusing Diff": 0, "Ironing Diff": -18})
		self.assertEqual(result["not_in_ipd_processes"], ["Printing"])


class TestWorkInProgressMetadata(TestCase):
	def test_inventory_and_query_fields_exist_in_effective_meta(self):
		from essdee_yrp.merch.report_inventory import field_inventory

		inventory = {row["key"]: row for row in field_inventory()}
		self.assertEqual(inventory["category"]["options"], "SD YRP Product Category")
		self.assertEqual(inventory["product_season"]["options"], "SD YRP Product Season")
		self.assertEqual(inventory["process_list"]["options"], "YRP Process")
		self.assertEqual(inventory["lot"]["source"], "SD YRP Lot.name")
		self.assertEqual(inventory["lot"]["options"], "SD YRP Lot")
		for doctype, fields in {
			"YRP Work Order": ["lot", "includes_packing", "is_rework", "first_dc_date", "last_grn_date"],
			"YRP Goods Received Note": ["packing_calculation_version", "against_id", "is_return"],
			"YRP Goods Received Note Item": ["quantity", "stock_qty", "received_type"],
			"YRP Item Production Detail": ["cutting_process", "stiching_process", "packing_combo", "set_item_attribute"],
		}.items():
			meta = frappe.get_meta(doctype)
			for fieldname in fields:
				self.assertIsNotNone(meta.get_field(fieldname), f"{doctype}.{fieldname}")
