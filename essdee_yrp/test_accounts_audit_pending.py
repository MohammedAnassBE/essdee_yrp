from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe
from frappe.utils import get_datetime

from essdee_yrp.accounts import audit_pending as dashboard


class TestAuditPendingFinishingPlans(TestCase):
	def test_dashboard_api_replaces_the_flat_report(self):
		self.assertTrue(callable(getattr(dashboard, "get_dashboard_data", None)))

	def test_dashboard_data_queries_only_partially_dispatched_when_requested(self):
		with (
			patch.object(dashboard, "require_access"),
			patch.object(dashboard.frappe, "get_list", return_value=[]) as get_all,
		):
			result = dashboard.get_dashboard_data.__wrapped__(show_partially_dispatched="1")

		self.assertEqual(
			get_all.call_args.kwargs["filters"],
			{"fp_status": ["in", ("Partially Dispatched",)]},
		)
		self.assertEqual(result["plans"], [])

	def test_dashboard_data_keeps_dispatched_defaults_when_partial_mode_is_off(self):
		with (
			patch.object(dashboard, "require_access"),
			patch.object(dashboard.frappe, "get_list", return_value=[]) as get_all,
		):
			dashboard.get_dashboard_data.__wrapped__(show_partially_dispatched="0")

		self.assertEqual(
			get_all.call_args.kwargs["filters"],
			{"fp_status": ["in", ("Dispatched", "Fully Dispatched")]},
		)

	def test_overdue_rows_exclude_exactly_seven_days_and_sort_oldest_first(self):
		as_of = get_datetime("2026-10-05 12:00:00")
		plans = [
			frappe._dict(name="FP-8", lot="LOT-8", item="Item 8", fp_status="Dispatched"),
			frappe._dict(name="FP-19", lot="LOT-19", item="Item 19", fp_status="Fully Dispatched"),
			frappe._dict(name="FP-7", lot="LOT-7", item="Item 7", fp_status="Dispatched"),
		]
		status_since = {
			"FP-8": get_datetime("2026-09-27 12:00:00"),
			"FP-19": get_datetime("2026-09-16 12:00:00"),
			"FP-7": get_datetime("2026-09-28 12:00:00"),
		}
		metrics = {
			"FP-8": {"total_cut": 100, "sewing_received": 98, "packed": 95, "dispatched": 80},
			"FP-19": {"total_cut": 200, "sewing_received": 195, "packed": 190, "dispatched": 188},
			"FP-7": {"total_cut": 50, "sewing_received": 49, "packed": 48, "dispatched": 40},
		}
		histories = {
			"FP-19": [
				frappe._dict(
					source_doctype="SD YRP Finishing Plan Dispatch",
					source_name="FPD-2",
					stock_entry="STE-2",
					posting_date="2026-09-16",
					posting_time="12:00:00",
					dispatch_boxes=2,
					dispatch_pieces=100,
					cancelled=1,
				),
				frappe._dict(
					source_doctype="SD YRP Finishing Plan Dispatch",
					source_name="FPD-1",
					stock_entry="STE-1",
					posting_date="2026-09-15",
					posting_time="12:00:00",
					dispatch_boxes=4,
					dispatch_pieces=188,
					cancelled=0,
					destination="WH-Main",
					operator="Jane Doe",
				),
			]
		}

		rows = dashboard._build_overdue_rows(plans, status_since, metrics, histories, as_of)

		self.assertEqual([row["name"] for row in rows], ["FP-19", "FP-8"])
		self.assertEqual(rows[0]["age_days"], 19)
		self.assertEqual(len(rows[0]["dispatch_history"]), 1)
		self.assertEqual(rows[0]["latest_dispatch"]["document"], "FPD-1")
		self.assertEqual(rows[1]["age_days"], 8)

	def test_summary_counts_each_status_and_oldest_age(self):
		rows = [
			{"fp_status": "Partially Dispatched", "age_days": 21},
			{"fp_status": "Fully Dispatched", "age_days": 19},
			{"fp_status": "Dispatched", "age_days": 15},
			{"fp_status": "Dispatched", "age_days": 8},
		]

		self.assertEqual(
			dashboard._summarize(rows),
			{
				"overdue": 4,
				"partially_dispatched": 1,
				"dispatched": 2,
				"fully_dispatched": 1,
				"oldest_days": 21,
			},
		)

	def test_plan_metrics_support_dynamic_and_legacy_packing(self):
		finishing_plan = SimpleNamespace(
			pieces_per_box=10,
			finishing_plan_details=[
				SimpleNamespace(cutting_qty=60, delivered_quantity=55),
				SimpleNamespace(cutting_qty=40, delivered_quantity=37),
			],
			finishing_plan_grn_details=[
				SimpleNamespace(quantity=4, dispatched=3),
				SimpleNamespace(quantity=2, dispatched=1),
			],
		)

		legacy = dashboard._build_plan_metrics(
			finishing_plan,
			frappe._dict(dynamic_ratio_packing=False),
			set_item_parts_count=2,
		)
		dynamic = dashboard._build_plan_metrics(
			finishing_plan,
			frappe._dict(
				dynamic_ratio_packing=True,
				total_packed=97,
				total_dispatched=91,
			),
			set_item_parts_count=2,
		)

		self.assertEqual(
			legacy,
			{"total_cut": 100.0, "sewing_received": 92.0, "packed": 120.0, "dispatched": 80.0},
		)
		self.assertEqual(
			dynamic,
			{"total_cut": 100.0, "sewing_received": 92.0, "packed": 194.0, "dispatched": 182.0},
		)

	def test_dynamic_dispatch_rows_keep_batch_boxes_and_size_pieces(self):
		rows = dashboard._build_dynamic_dispatch_rows(
			[
				{
					"finishing_plan": "FP-1",
					"colour": "Black",
					"pieces_per_box": 50,
					"box_quantity": 2,
					"size_pieces": {"L": 100, "XL": 95},
				},
				{
					"finishing_plan": "FP-OTHER",
					"colour": "Navy",
					"pieces_per_box": 40,
					"box_quantity": 1,
					"size_pieces": {"M": 40},
				},
			],
			"FP-1",
		)

		self.assertEqual(
			rows,
			[
				{"size": "L", "detail": "Black", "pieces_per_box": 50.0, "boxes": 2.0, "pieces": 100.0},
				{"size": "XL", "detail": "Black", "pieces_per_box": 50.0, "boxes": 2.0, "pieces": 95.0},
			],
		)

	def test_dynamic_dispatch_rows_allow_unscoped_batches_for_direct_dispatch(self):
		rows = dashboard._build_dynamic_dispatch_rows(
			[
				{
					"colour": "Black",
					"pieces_per_box": 50,
					"box_quantity": 2,
					"size_pieces": {"L": 100},
				},
				{
					"finishing_plan": "FP-OTHER",
					"colour": "Navy",
					"pieces_per_box": 40,
					"box_quantity": 1,
					"size_pieces": {"M": 40},
				},
			],
			"FP-1",
			include_unscoped=True,
		)

		self.assertEqual(
			rows,
			[
				{
					"size": "L",
					"detail": "Black",
					"pieces_per_box": 50.0,
					"boxes": 2.0,
					"pieces": 100.0,
				}
			],
		)

	def test_pending_breakdown_keeps_set_parts_and_categories_separate(self):
		ocr_data = {
			"Top": {
				"data": {
					"Navy (Royal) @ Top": {
						"values": {
							"S": {
								"loose_piece": 4,
								"loose_piece_set": 2,
								"rejected": 1,
								"pending": 3,
							},
							"M": {
								"loose_piece": 0,
								"loose_piece_set": 0,
								"rejected": 0,
								"pending": 0,
							},
						}
					},
					"White (Royal) @ Top": {
						"values": {
							"S": {
								"loose_piece": 0,
								"loose_piece_set": 0,
								"rejected": 0,
								"pending": 0,
							},
							"M": {
								"loose_piece": 5,
								"loose_piece_set": 0,
								"rejected": 2,
								"pending": 0,
							},
						}
					},
				}
			},
			"Bottom": {
				"data": {
					"Black (Royal) @ Bottom": {
						"values": {
							"S": {
								"loose_piece": 1,
								"loose_piece_set": 1,
								"rejected": 0,
								"pending": 4,
							},
							"M": {
								"loose_piece": 0,
								"loose_piece_set": 0,
								"rejected": 0,
								"pending": 0,
							},
						}
					}
				}
			},
		}

		result = dashboard._build_pending_breakdown(ocr_data, ["S", "M"])

		self.assertEqual([part["name"] for part in result["parts"]], ["Top", "Bottom"])
		top = result["parts"][0]
		self.assertEqual(top["sizes"], ["S", "M"])
		self.assertEqual(
			[category["key"] for category in top["categories"]],
			["loose_piece", "loose_piece_set", "rejected", "pending"],
		)
		self.assertEqual(
			top["categories"][0],
			{
				"key": "loose_piece",
				"label": "Loose Piece",
				"rows": [
					{"colour": "Navy (Royal)", "values": [4.0, 0.0], "total": 4.0},
					{"colour": "White (Royal)", "values": [0.0, 5.0], "total": 5.0},
				],
				"size_totals": [4.0, 5.0],
				"total": 9.0,
			},
		)
		self.assertEqual(top["categories"][1]["total"], 2.0)
		self.assertEqual(top["categories"][2]["total"], 3.0)
		self.assertEqual(top["categories"][3]["total"], 3.0)
		self.assertEqual(result["parts"][1]["categories"][3]["total"], 4.0)

	def test_dispatch_detail_rejects_a_document_outside_the_plan(self):
		with (
			patch.object(dashboard, "require_access"),
			patch.object(dashboard.frappe, "get_doc"),
			patch.object(dashboard.frappe.db, "exists", return_value=False),
		):
			with self.assertRaises(frappe.PermissionError):
				dashboard.get_dispatch_detail.__wrapped__(
					finishing_plan="FP-1",
					source_doctype="SD YRP Finishing Plan Dispatch",
					source_name="FPD-OTHER",
					stock_entry="STE-OTHER",
				)

	def test_can_view_requires_accounts_role_and_finishing_plan_read(self):
		for roles, readable, expected in (
			(["Stock User"], True, False),
			(["Accounts User"], False, False),
			(["Accounts User"], True, True),
			(["Accounts Manager"], True, True),
			(["System Manager"], True, True),
		):
			with (
				self.subTest(roles=roles, readable=readable),
				patch.object(frappe, "get_roles", return_value=roles),
				patch.object(frappe, "has_permission", return_value=readable),
			):
				self.assertEqual(dashboard.can_view(), expected)

	def test_all_endpoints_reject_missing_accounts_role_or_plan_read(self):
		calls = (
			lambda: dashboard.get_dashboard_data.__wrapped__(),
			lambda: dashboard.get_pending_breakdown.__wrapped__("FP-1"),
			lambda: dashboard.get_dispatch_detail.__wrapped__(
				"FP-1", "SD YRP Finishing Plan", "FP-1", "STE-1"
			),
		)
		for roles, readable in ((["Stock User"], True), (["Accounts User"], False)):
			for call in calls:
				with (
					self.subTest(roles=roles),
					patch.object(frappe, "get_roles", return_value=roles),
					patch.object(frappe, "has_permission", return_value=readable),
					patch.object(frappe, "get_list") as query,
				):
					with self.assertRaises(frappe.PermissionError):
						call()
					# Frappe may lazily query Translation while constructing the permission error.
					self.assertTrue(
						all(query_call.args[0] == "Translation" for query_call in query.call_args_list)
					)

	def test_pending_detail_checks_plan_read_before_loading_ocr(self):
		with (
			patch.object(dashboard, "require_access"),
			patch.object(frappe, "get_doc") as get_doc,
			patch.object(dashboard, "get_fp_ocr_details") as ocr,
		):
			get_doc.return_value.check_permission.side_effect = frappe.PermissionError
			with self.assertRaises(frappe.PermissionError):
				dashboard.get_pending_breakdown.__wrapped__("FP-PRIVATE")
			ocr.assert_not_called()

	def test_dispatch_detail_checks_plan_read_before_loading_dispatch(self):
		with (
			patch.object(dashboard, "require_access"),
			patch.object(frappe, "get_doc") as get_doc,
			patch.object(frappe.db, "exists") as exists,
		):
			get_doc.return_value.check_permission.side_effect = frappe.PermissionError
			with self.assertRaises(frappe.PermissionError):
				dashboard.get_dispatch_detail.__wrapped__(
					"FP-PRIVATE", "SD YRP Finishing Plan", "FP-PRIVATE", "STE-1"
				)
			exists.assert_not_called()

	def test_dashboard_uses_persisted_date_excludes_undated_and_permission_filtered_rows(self):
		plans = [
			frappe._dict(
				name="FP-OLD",
				lot="LOT",
				item="ITEM",
				fp_status="Dispatched",
				fp_status_since="2026-09-15 12:00:00",
			),
			frappe._dict(
				name="FP-SEVEN",
				lot="LOT",
				item="ITEM",
				fp_status="Dispatched",
				fp_status_since="2026-09-28 12:00:00",
			),
			frappe._dict(
				name="FP-UNDATED", lot="LOT", item="ITEM", fp_status="Dispatched", fp_status_since=None
			),
			frappe._dict(
				name="FP-PRIVATE",
				lot="LOT",
				item="ITEM",
				fp_status="Dispatched",
				fp_status_since="2026-09-01 12:00:00",
			),
		]
		with (
			patch.object(dashboard, "require_access"),
			patch.object(frappe, "get_list", return_value=plans) as query,
			patch.object(
				frappe,
				"has_permission",
				side_effect=lambda *args, **kwargs: kwargs.get("doc") != "FP-PRIVATE",
			),
			patch.object(frappe, "get_all", side_effect=AssertionError("No Version/runtime history query")),
			patch.object(dashboard, "now_datetime", return_value=get_datetime("2026-10-05 12:00:00")),
			patch.object(dashboard, "_get_plan_metrics", return_value={"total_cut": 10, "packed": 9}),
			patch.object(dashboard, "_get_dispatch_histories", return_value={}),
		):
			result = dashboard.get_dashboard_data.__wrapped__()
		self.assertEqual([row["name"] for row in result["plans"]], ["FP-OLD"])
		self.assertEqual(result["plans"][0]["status_since"], "2026-09-15")
		self.assertEqual(result["plans"][0]["age_days"], 20)
		self.assertEqual(
			result["summary"],
			{
				"overdue": 1,
				"partially_dispatched": 0,
				"dispatched": 1,
				"fully_dispatched": 0,
				"oldest_days": 20,
			},
		)
		self.assertEqual(query.call_args.args, ("SD YRP Finishing Plan",))
		self.assertIn("fp_status_since", query.call_args.kwargs["fields"])

	def test_pending_endpoint_returns_all_parts_and_finishing_plan(self):
		with (
			patch.object(dashboard, "require_access"),
			patch.object(frappe, "get_doc"),
			patch.object(dashboard, "get_fp_ocr_details", return_value=({"Top": {"data": {}}}, {}, ["S"])),
		):
			result = dashboard.get_pending_breakdown.__wrapped__("FP-1")
		self.assertEqual(result["finishing_plan"], "FP-1")
		self.assertEqual(result["parts"][0]["name"], "Top")
		self.assertEqual(result["parts"][0]["sizes"], ["S"])
		self.assertEqual([row["total"] for row in result["parts"][0]["categories"]], [0, 0, 0, 0])

	def test_legacy_dispatch_rows_group_variants_and_keep_explicit_piece_quantity(self):
		result = dashboard._build_legacy_dispatch_rows(
			[
				{"item_variant": "A", "quantity": 2, "packing_piece_quantity": 0},
				{"item_variant": "B", "quantity": 1, "packing_piece_quantity": 17},
			],
			{"A": {"Size": "L", "Colour": "Navy"}, "B": {"Size": "L", "Colour": "Navy"}},
			"Size",
			"Colour",
			10,
			2,
		)
		self.assertEqual(
			result, [{"size": "L", "detail": "Navy", "pieces_per_box": 10.0, "boxes": 3.0, "pieces": 57.0}]
		)

	def test_dispatch_detail_dynamic_response_uses_matching_log_totals(self):
		plan = frappe._dict(item="ITEM", pieces_per_box=10)
		plan.check_permission = lambda ptype: None
		log = frappe._dict(posting_date="2026-09-15", dispatch_boxes=2, dispatch_pieces=95)
		meta = frappe._dict(
			owner="jane@example.com",
			transfer_supplier="Destination",
			packing_batch_dispatch_json=[
				{
					"finishing_plan": "FP-1",
					"colour": "Navy",
					"pieces_per_box": 50,
					"box_quantity": 2,
					"size_pieces": {"L": 95},
				},
			],
		)
		with (
			patch.object(dashboard, "require_access"),
			patch.object(frappe, "get_doc", return_value=plan),
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(frappe.db, "get_value", side_effect=[log, "Jane"]),
			patch.object(dashboard, "_get_stock_entry_meta", return_value=meta),
		):
			result = dashboard.get_dispatch_detail.__wrapped__(
				"FP-1", "SD YRP Finishing Plan Dispatch", "FPD-1", "STE-1"
			)
		self.assertEqual(result["document"], "FPD-1")
		self.assertEqual(result["posting_date"], "2026-09-15")
		self.assertEqual(result["destination"], "Destination")
		self.assertEqual(result["operator"], "Jane")
		self.assertEqual(result["total_dispatched"], 95)
		self.assertEqual(result["totals"], {"boxes": 2.0, "pieces": 95.0})
		self.assertEqual(
			result["rows"],
			[{"size": "L", "detail": "Navy", "pieces_per_box": 50.0, "boxes": 2.0, "pieces": 95.0}],
		)

	def test_json_dispatch_batches_reject_non_list_and_malformed_values(self):
		for raw in (None, "not-json", '{"size_pieces": {}}', "42"):
			with self.subTest(raw=raw):
				self.assertEqual(dashboard._as_json_list(raw), [])
		self.assertEqual(dashboard._as_json_list('[{"colour": "Navy"}]'), [{"colour": "Navy"}])

	def test_history_queries_erp_logs_and_submitted_stock_entry_metadata(self):
		log = frappe._dict(
			parent="FP-1",
			stock_entry="STE-1",
			source_doctype="SD YRP Finishing Plan Dispatch",
			source_name="FPD-1",
		)
		entry = frappe._dict(
			name="STE-1", transfer_supplier="Supplier", to_warehouse="Warehouse", owner="jane@example.com"
		)
		with patch.object(
			frappe,
			"get_all",
			side_effect=[
				[log],
				[entry],
				[frappe._dict(name="jane@example.com", full_name="Jane")],
			],
		) as query:
			result = dashboard._get_dispatch_histories(["FP-1"])
		self.assertEqual(result["FP-1"][0]["destination"], "Supplier")
		self.assertEqual(result["FP-1"][0]["operator"], "Jane")
		self.assertEqual(query.call_args_list[0].args, ("SD YRP Finishing Plan Dispatch Log",))
		self.assertEqual(query.call_args_list[0].kwargs["filters"]["parenttype"], "SD YRP Finishing Plan")
		self.assertEqual(query.call_args_list[0].kwargs["filters"]["cancelled"], 0)
		self.assertEqual(query.call_args_list[1].args, ("YRP Stock Entry",))
		self.assertEqual(query.call_args_list[1].kwargs["filters"]["docstatus"], 1)

	def test_dispatch_detail_legacy_direct_uses_erp_item_attributes(self):
		plan = frappe._dict(item="ITEM", pieces_per_box=10, production_detail="IPD-1")
		plan.check_permission = lambda ptype: None
		log = frappe._dict(posting_date="2026-09-15", dispatch_boxes=2, dispatch_pieces=40)
		with (
			patch.object(dashboard, "require_access"),
			patch.object(frappe, "get_doc", return_value=plan),
			patch.object(frappe.db, "exists", return_value=True),
			patch.object(
				frappe.db,
				"get_value",
				side_effect=[log, frappe._dict(primary_item_attribute="Size", dependent_attribute="Colour")],
			),
			patch.object(dashboard, "_get_stock_entry_meta", return_value={}),
			patch.object(
				frappe,
				"get_all",
				side_effect=[
					[frappe._dict(item="VAR-1", qty=2)],
					[
						frappe._dict(parent="VAR-1", attribute="Size", attribute_value="L"),
						frappe._dict(parent="VAR-1", attribute="Colour", attribute_value="Navy"),
					],
				],
			) as query,
			patch.object(dashboard, "get_set_item_parts_count", return_value=2),
		):
			result = dashboard.get_dispatch_detail.__wrapped__(
				"FP-1", "SD YRP Finishing Plan", "FP-1", "STE-1"
			)
		self.assertEqual(result["document"], "STE-1")
		self.assertEqual(
			result["rows"],
			[{"size": "L", "detail": "Navy", "pieces_per_box": 10.0, "boxes": 2.0, "pieces": 40.0}],
		)
		self.assertEqual(query.call_args_list[0].args, ("YRP Stock Entry Detail",))
