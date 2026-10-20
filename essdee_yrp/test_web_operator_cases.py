from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.cutting import web_workspace as cutting
from essdee_yrp.finishing import web_dispatch
from essdee_yrp.sewing import read_models as sewing


class TestSewingEntryPaging(TestCase):
	def test_database_page_is_bounded_stable_and_permission_filtered(self):
		with (
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe, "get_list", return_value=[]) as get_list,
		):
			sewing._entries([frappe._dict(name="SP-1")], start=100, page_length=101)
		options = get_list.call_args.kwargs
		self.assertEqual(options["limit_start"], 100)
		self.assertEqual(options["limit_page_length"], 101)
		self.assertEqual(options["order_by"], "entry_date desc, entry_time desc, creation desc, name desc")
		self.assertEqual(options["filters"]["sewing_plan"], ["in", ["SP-1"]])

	def test_only_page_rows_load_details_and_lookahead_sets_has_more(self):
		entries = [frappe._dict(name=f"ENTRY-{index}") for index in range(101)]
		with (
			patch.object(sewing, "_plans", return_value=[]) as plans,
			patch.object(sewing, "_entries", return_value=entries) as read_entries,
			patch.object(sewing, "_details", return_value=[]) as details,
			patch.object(sewing, "_metadata", return_value=({}, {})),
			patch.object(sewing, "_variant_attributes", return_value={}),
			patch.object(frappe.db, "get_single_value", return_value=0),
		):
			page = sewing.get_sewing_plan_entry_page("S-0172", lot_name="LOT-1", start="100")
		plans.assert_called_once_with("S-0172", lots=["LOT-1"])
		self.assertEqual(read_entries.call_args.kwargs["page_length"], 101)
		self.assertEqual(read_entries.call_args.kwargs["start"], 100)
		self.assertEqual(len(details.call_args.args[0]), 100)
		self.assertTrue(page["has_more"])
		self.assertEqual(page["next_start"], 200)

	def test_desk_entries_keep_every_entry_as_a_plain_mapping(self):
		with (
			patch.object(sewing, "_plans", return_value=[]),
			patch.object(sewing, "_entries", return_value=[]) as read_entries,
			patch.object(sewing, "_details", return_value=[]),
			patch.object(sewing, "_metadata", return_value=({}, {})),
			patch.object(sewing, "_variant_attributes", return_value={}),
			patch.object(frappe.db, "get_single_value", return_value=0),
		):
			entries = sewing.get_sewing_plan_entries("S-0172")
		self.assertEqual(read_entries.call_args.kwargs["page_length"], 0)
		self.assertEqual(entries, {})


class TestFinishingDispatchDefaults(TestCase):
	def setUp(self):
		permission = patch.object(frappe, "has_permission", return_value=True)
		permission.start()
		self.addCleanup(permission.stop)

	def test_unreadable_plans_do_not_block_the_dispatch_workspace(self):
		with patch.object(frappe, "has_permission", return_value=False):
			self.assertEqual(web_dispatch.dispatch_defaults([{"doc_name": "FP-1"}]), {"from_supplier": ""})

	def test_common_finishing_location_prefills_source_supplier(self):
		with patch.object(
			frappe,
			"get_list",
			return_value=[
				frappe._dict(name="FP-1", delivery_location="SUP-1"),
				frappe._dict(name="FP-2", delivery_location="SUP-1"),
			],
		):
			self.assertEqual(
				web_dispatch.dispatch_defaults([{"doc_name": "FP-1"}, {"doc_name": "FP-2"}]),
				{"from_supplier": "SUP-1"},
			)

	def test_mixed_or_unreadable_plan_locations_need_explicit_source(self):
		for locations in (
			[frappe._dict(name="FP-1", delivery_location="SUP-1")],
			[
				frappe._dict(name="FP-1", delivery_location="SUP-1"),
				frappe._dict(name="FP-2", delivery_location="SUP-2"),
			],
		):
			with patch.object(frappe, "get_list", return_value=locations):
				self.assertEqual(
					web_dispatch.dispatch_defaults([{"doc_name": "FP-1"}, {"doc_name": "FP-2"}]),
					{"from_supplier": ""},
				)


class TestCuttingMovementDraftCheck(TestCase):
	def test_generate_rechecks_draft_before_expensive_bundle_read(self):
		plan = frappe._dict(name="CP-1", lot="LOT-1")
		context = frappe._dict(source_supplier="SUP-1")
		with (
			patch.object(cutting, "_get_plan", return_value=plan),
			patch.object(cutting, "_require_active_plan"),
			patch.object(cutting, "_plan_context", return_value=context),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe.db, "exists", return_value="CPM-1") as exists,
			patch.object(cutting, "get_cut_bundle_unmoved_data") as generate,
		):
			with self.assertRaisesRegex(
				frappe.ValidationError,
				"Submit or delete draft Cut Panel Movement CPM-1 for SUP-1 / LOT-1 first.",
			):
				cutting.generate_movement_bundles("CP-1")
		generate.assert_not_called()
		exists.assert_called_once_with(
			cutting.MOVEMENT_DOCTYPE,
			{"lot": "LOT-1", "from_warehouse": "SUP-1", "docstatus": 0},
		)

	def test_open_returns_same_draft_message_without_generating(self):
		with (
			patch.object(cutting, "_get_plan", return_value=frappe._dict(lot="LOT-1")),
			patch.object(cutting, "_require_active_plan"),
			patch.object(cutting, "_plan_context", return_value=frappe._dict(source_supplier="SUP-1")),
			patch.object(cutting, "_movement_editor_payload", return_value={}),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe.db, "exists", return_value="CPM-1"),
		):
			self.assertEqual(
				cutting.get_movement_editor("CP-1")["create_blocker"],
				"Submit or delete draft Cut Panel Movement CPM-1 for SUP-1 / LOT-1 first.",
			)
