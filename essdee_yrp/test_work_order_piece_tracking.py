"""Regression coverage for deterministic Work Order piece replay."""

from unittest import TestCase
from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp import work_order_piece_tracking as piece_tracking
from essdee_yrp.finishing.rebuild import (
	get_configured_cutting_process,
	get_process_work_orders,
	rebuild_finishing_plan,
)
from essdee_yrp.test_packing_grn_loose_piece import SIZE_M, attributes
from essdee_yrp.work_order_piece_tracking import (
	audit_migrated_piece_tracking,
	compare_work_order_piece_tracking,
	on_delivery_challan_submit,
	on_goods_received_note_submit,
	rebuild_work_order_piece_tracking,
)


class TestWorkOrderPieceTracking(IntegrationTestCase):
	@patch("essdee_yrp.work_order_piece_tracking.rebuild_work_order_piece_tracking")
	@patch("essdee_yrp.work_order_piece_tracking.frappe.db.get_value", return_value=None)
	def test_generic_base_work_orders_do_not_enter_essdee_piece_replay(self, _get_value, rebuild):
		on_delivery_challan_submit(frappe._dict(work_order="BASE-WO"))
		on_goods_received_note_submit(frappe._dict(against="YRP Work Order", against_id="BASE-WO"))
		rebuild.assert_not_called()

	@patch("essdee_yrp.finishing.rebuild.sync_finishing_plans_from_work_order")
	@patch("essdee_yrp.work_order_piece_tracking._rebuild_lot_stage_quantities")
	@patch("essdee_yrp.work_order_piece_tracking._apply_projection")
	@patch("essdee_yrp.work_order_piece_tracking.calculate_work_order_piece_tracking")
	@patch("essdee_yrp.work_order_piece_tracking.frappe.get_doc")
	def test_finishing_sync_runs_only_after_projection_and_lot_rebuild(
		self,
		get_doc,
		calculate_projection,
		apply_projection,
		rebuild_lot,
		sync_finishing,
	):
		calls = []
		doc = MagicMock(name="WorkOrder")
		doc.name = "WO-1"
		doc.docstatus = 1
		doc.lot = "LOT-1"
		get_doc.return_value = doc
		calculate_projection.side_effect = lambda _name: (
			calls.append("calculate")
			or {
				"total_delivered": 10,
				"total_received": 9,
				"received_types": {"Accepted": 9},
				"tracking": [1],
			}
		)
		apply_projection.side_effect = lambda *_args: calls.append("persist_projection")
		rebuild_lot.side_effect = lambda *_args: calls.append("rebuild_lot")
		sync_finishing.side_effect = lambda *_args: calls.append("sync_finishing") or ["FP-1"]

		result = rebuild_work_order_piece_tracking("WO-1", check_permission=False)

		self.assertEqual(
			calls,
			[
				"calculate",
				"persist_projection",
				"rebuild_lot",
				"sync_finishing",
			],
		)
		self.assertEqual(
			get_doc.call_args_list[:2],
			[
				call("YRP Work Order", "WO-1", for_update=True),
				call("SD YRP Lot", "LOT-1", for_update=True),
			],
		)
		self.assertEqual(result["finishing_plans"], ["FP-1"])

	def test_migrated_cutting_printing_types_and_returns_match(self):
		# Packing oracles (WO-2627-00478, WO-2526-02687-1) intentionally diverge from F15:
		# F15 credited each packing GRN's box count to every packing colour, while replay
		# records the GRN's real pieces. See TestMigratedPackingReceipt.
		oracles = (
			"WO-2526-02637-2",  # cutting panels -> completed pieces
			"WO-2627-00005",  # direct printing DC/GRN
			"WO-2526-02445",  # multiple GRN received types
			"WO-2627-00365",  # accumulated panel return GRNs
			"WO-2627-00604-1",  # fractional legacy quantities in Int counters
		)
		missing = [name for name in oracles if not frappe.db.exists("YRP Work Order", name)]
		if missing:
			self.skipTest(f"Migrated piece-tracking oracles unavailable: {', '.join(missing)}")

		for name in oracles:
			with self.subTest(work_order=name):
				comparison = compare_work_order_piece_tracking(name)
				self.assertTrue(comparison["matches"], comparison)

	def test_rebuild_is_idempotent_and_does_not_duplicate_tracking_rows(self):
		name = "WO-2627-00005"
		if not frappe.db.exists("YRP Work Order", {"name": name, "docstatus": 1}):
			self.skipTest(f"Migrated Work Order oracle {name} is unavailable")

		first = rebuild_work_order_piece_tracking(name, check_permission=False)
		first_doc = frappe.get_doc("YRP Work Order", name)
		first_rows = [
			(
				row.item_variant,
				row.delivered_quantity,
				row.received_qty,
				row.against,
				row.against_id,
			)
			for row in first_doc.work_order_track_pieces
		]

		second = rebuild_work_order_piece_tracking(name, check_permission=False)
		second_doc = frappe.get_doc("YRP Work Order", name)
		second_rows = [
			(
				row.item_variant,
				row.delivered_quantity,
				row.received_qty,
				row.against,
				row.against_id,
			)
			for row in second_doc.work_order_track_pieces
		]

		self.assertEqual(first, second)
		self.assertEqual(first_rows, second_rows)
		self.assertEqual(len(second_rows), second["source_rows"])

	def test_finishing_rebuild_retry_is_idempotent_and_has_unique_projection_rows(self):
		name = "FP-2526-00238"
		if not frappe.db.exists("SD YRP Finishing Plan", name):
			self.skipTest(f"Retained Finishing Plan oracle {name} is unavailable")

		def snapshot():
			doc = frappe.get_doc("SD YRP Finishing Plan", name)
			ignored = {
				"name",
				"owner",
				"creation",
				"modified",
				"modified_by",
				"docstatus",
				"idx",
				"parent",
				"parentfield",
				"parenttype",
				"doctype",
			}
			return {
				fieldname: [
					{key: value for key, value in row.as_dict().items() if key not in ignored}
					for row in doc.get(fieldname) or []
				]
				for fieldname in (
					"finishing_plan_details",
					"finishing_plan_reworked_details",
				)
			}

		rebuild_finishing_plan(name, check_permission=False)
		first = snapshot()
		rebuild_finishing_plan(name, check_permission=False)
		second = snapshot()

		self.assertEqual(first, second)
		for fieldname, rows in second.items():
			keys = [
				(row.get("item_variant"), frappe.as_json(row.get("set_combination") or {})) for row in rows
			]
			self.assertEqual(len(keys), len(set(keys)), f"Duplicate {fieldname} projection rows")

	def test_recent_historical_replay_has_no_quantity_mismatches(self):
		result = audit_migrated_piece_tracking(limit=100)
		self.assertFalse(result["errors"], result["errors"])
		self.assertFalse(result["mismatches"], result["mismatches"])

	def test_returned_cutting_and_stitching_sources_refresh_finishing_plan(self):
		oracles = (
			("WO-2627-00365", "Stitching"),
			("WO-2526-02367-1", "Cutting"),
		)
		missing = [
			name
			for name, _source_type in oracles
			if not frappe.db.exists("YRP Work Order", {"name": name, "docstatus": 1})
		]
		if missing:
			self.skipTest(f"Migrated return oracles unavailable: {', '.join(missing)}")

		for work_order_name, source_type in oracles:
			with self.subTest(work_order=work_order_name):
				work_order = frappe.get_doc("YRP Work Order", work_order_name)
				finishing_plan_name = frappe.db.get_value(
					"SD YRP Finishing Plan", {"lot": work_order.lot}, "name"
				)
				self.assertTrue(finishing_plan_name)
				self.assertTrue(
					frappe.db.exists(
						"YRP Goods Received Note",
						{
							"against": "YRP Work Order",
							"against_id": work_order.name,
							"docstatus": 1,
							"is_return": 1,
						},
					)
				)

				rebuild_work_order_piece_tracking(work_order.name, check_permission=False)
				finishing_plan = frappe.get_doc("SD YRP Finishing Plan", finishing_plan_name)

				if source_type == "Stitching":
					process = frappe.db.get_single_value("SD YRP MRP Settings", "finishing_inward_process")
					expected_delivered, expected_received = _source_totals(
						get_process_work_orders(process, work_order.lot)
					)
					self.assertEqual(
						sum(row.inward_quantity for row in finishing_plan.finishing_plan_details),
						expected_delivered,
					)
					self.assertEqual(
						sum(row.delivered_quantity for row in finishing_plan.finishing_plan_details),
						expected_received,
					)
				else:
					process = get_configured_cutting_process(
						production_detail=finishing_plan.production_detail,
						lot=work_order.lot,
					)
					_expected_delivered, expected_received = _source_totals(
						get_process_work_orders(process, work_order.lot)
					)
					self.assertEqual(
						sum(row.cutting_qty for row in finishing_plan.finishing_plan_details),
						expected_received,
					)


def _source_totals(work_orders):
	delivered = 0
	received = 0
	for name in work_orders:
		for row in frappe.get_doc("YRP Work Order", name).work_order_calculated_items:
			delivered += row.delivered_quantity
			received += row.received_qty
	return delivered, received


class TestMigratedPackingReceipt(TestCase):
	"""F15 packing GRNs stored box counts per packing colour; replay uses real pieces."""

	def _state(self, received_snapshot=()):
		calculated = [
			frappe._dict(
				name=f"CALC-{colour}",
				idx=idx,
				item_variant=f"VEST-{colour}-M",
				quantity=planned,
				set_combination=f'{{"major_colour":"{colour}"}}',
			)
			for colour, idx, planned, _delivered, _received in SIZE_M
		]
		work_order = frappe._dict(
			work_order_calculated_items=calculated, work_order_track_pieces=list(received_snapshot)
		)
		ipd = frappe._dict(primary_item_attribute="Size", is_set_item=0)
		with (
			patch.object(piece_tracking, "get_variant_attr_details", side_effect=attributes),
			patch.object(piece_tracking, "get_parent_item", return_value="VEST"),
			patch.object(piece_tracking.PieceState, "_initial_panel_structures", return_value=({}, {})),
		):
			return piece_tracking.PieceState(work_order, ipd)

	@staticmethod
	def _deliver(state, name, posting_time, quantities):
		challan = frappe._dict(name=name, posting_date="2026-10-14", posting_time=posting_time)
		for colour, quantity in quantities.items():
			state.add_delivery(f"VEST-{colour}-M", {"major_colour": colour}, quantity, challan)

	@staticmethod
	def _grn(name, posting_time, pieces, mapped=False):
		return frappe._dict(
			name=name,
			posting_date="2026-10-14",
			posting_time=posting_time,
			includes_packing=1,
			items=[
				frappe._dict(
					item_variant="BOX-M", quantity=pieces / 5, stock_qty=pieces, received_type="Accepted"
				)
			],
			grn_deliverables=[
				frappe._dict(
					item_variant="VEST-Loose Piece-M",
					quantity=pieces,
					goods_received_note_item="OUT-M" if mapped else None,
				)
			],
		)

	def _replay_fp_2627_00244(self, snapshot=()):
		state = self._state(snapshot)
		colours = ("Soft Orange", "Liver", "Wenge", "Dark Grey", "Olive", "Black")
		with (
			patch.object(piece_tracking, "get_variant_attr_details", side_effect=attributes),
			patch.object(piece_tracking, "is_dynamic_packing_grn", return_value=False),
		):
			self._deliver(state, "DC-2627-05831", "09:43:41", dict.fromkeys(colours, 350))
			piece_tracking._apply_packing_receipt(state, self._grn("GRN-2627-08000", "09:45:25", 2090))
			self._deliver(
				state,
				"DC-2627-05832",
				"09:49:11",
				{"Soft Orange": 100, "Wenge": 100, "Olive": 115, "Black": 200},
			)
			piece_tracking._apply_packing_receipt(state, self._grn("GRN-2627-08001", "09:49:42", 525))
			self._deliver(
				state,
				"DC-2026-00012",
				"12:16:14",
				{"Soft Orange": 300, "Liver": 386, "Wenge": 154, "Dark Grey": 66, "Olive": 439, "Black": 453},
			)
		return {data["item_variant"].split("-")[1]: data for data in state.rows}

	def test_migrated_box_history_is_replayed_as_real_pieces(self):
		box_history = [
			frappe._dict(
				against="YRP Goods Received Note",
				against_id="GRN-2627-08000",
				item_variant=f"VEST-{colour}-M",
				received_qty=418,
				set_combination=f'{{"major_colour":"{colour}"}}',
			)
			for colour, *_rest in SIZE_M
		]
		rows = self._replay_fp_2627_00244(box_history)

		self.assertEqual(
			[rows[colour]["received"] for colour, *_rest in SIZE_M], [450, 350, 450, 350, 0, 465, 550]
		)
		self.assertEqual(
			[rows[colour]["delivered"] - rows[colour]["received"] for colour, *_rest in SIZE_M],
			[300, 386, 154, 66, 0, 439, 453],
		)

	def test_mapped_packing_grn_keeps_its_consumed_rows(self):
		state = self._state()
		grn = self._grn("YRP-GRN-1", "10:00:00", 500, mapped=True)
		grn.grn_deliverables = [
			frappe._dict(
				item_variant="VEST-Black-M", set_combination='{"major_colour":"Black"}', quantity=453
			),
			frappe._dict(
				item_variant="VEST-Olive-M", set_combination='{"major_colour":"Olive"}', quantity=47
			),
		]
		for row in grn.grn_deliverables:
			row.goods_received_note_item = "OUT-M"
		with (
			patch.object(piece_tracking, "get_variant_attr_details", side_effect=attributes),
			patch.object(piece_tracking, "is_dynamic_packing_grn", return_value=False),
			patch.object(piece_tracking.frappe.db, "get_single_value", return_value="Accepted"),
		):
			piece_tracking._apply_packing_receipt(state, grn)

		received = {data["item_variant"]: data["received"] for data in state.rows if data["received"]}
		self.assertEqual(received, {"VEST-Black-M": 453, "VEST-Olive-M": 47})
