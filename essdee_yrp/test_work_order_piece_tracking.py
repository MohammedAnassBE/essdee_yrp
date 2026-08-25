"""Regression coverage for deterministic Work Order piece replay."""

from unittest.mock import MagicMock, call, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.work_order_piece_tracking import (
	audit_migrated_piece_tracking,
	compare_work_order_piece_tracking,
	on_delivery_challan_submit,
	on_goods_received_note_submit,
	rebuild_work_order_piece_tracking,
)
from essdee_yrp.finishing.rebuild import (
	get_configured_cutting_process,
	get_process_work_orders,
)


class TestWorkOrderPieceTracking(IntegrationTestCase):
	@patch("essdee_yrp.work_order_piece_tracking.rebuild_work_order_piece_tracking")
	@patch("essdee_yrp.work_order_piece_tracking.frappe.db.get_value", return_value=None)
	def test_generic_base_work_orders_do_not_enter_essdee_piece_replay(
		self, _get_value, rebuild
	):
		on_delivery_challan_submit(frappe._dict(work_order="BASE-WO"))
		on_goods_received_note_submit(
			frappe._dict(against="Work Order", against_id="BASE-WO")
		)
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
				call("Work Order", "WO-1", for_update=True),
				call("Lot", "LOT-1", for_update=True),
			],
		)
		self.assertEqual(result["finishing_plans"], ["FP-1"])

	def test_migrated_cutting_printing_packing_types_and_returns_match(self):
		oracles = (
			"WO-2526-02637-2",  # cutting panels -> completed pieces
			"WO-2627-00005",  # direct printing DC/GRN
			"WO-2627-00478",  # grouped ironing + packing
			"WO-2526-02445",  # multiple GRN received types
			"WO-2627-00365",  # accumulated panel return GRNs
			"WO-2526-02687-1",  # set-item packing expansion + returns
			"WO-2627-00604-1",  # fractional legacy quantities in Int counters
		)
		missing = [name for name in oracles if not frappe.db.exists("Work Order", name)]
		if missing:
			self.skipTest(f"Migrated piece-tracking oracles unavailable: {', '.join(missing)}")

		for name in oracles:
			with self.subTest(work_order=name):
				comparison = compare_work_order_piece_tracking(name)
				self.assertTrue(comparison["matches"], comparison)

	def test_rebuild_is_idempotent_and_does_not_duplicate_tracking_rows(self):
		name = "WO-2627-00005"
		if not frappe.db.exists("Work Order", {"name": name, "docstatus": 1}):
			self.skipTest(f"Migrated Work Order oracle {name} is unavailable")

		first = rebuild_work_order_piece_tracking(name, check_permission=False)
		first_doc = frappe.get_doc("Work Order", name)
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
		second_doc = frappe.get_doc("Work Order", name)
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
			if not frappe.db.exists("Work Order", {"name": name, "docstatus": 1})
		]
		if missing:
			self.skipTest(f"Migrated return oracles unavailable: {', '.join(missing)}")

		for work_order_name, source_type in oracles:
			with self.subTest(work_order=work_order_name):
				work_order = frappe.get_doc("Work Order", work_order_name)
				finishing_plan_name = frappe.db.get_value(
					"Finishing Plan", {"lot": work_order.lot}, "name"
				)
				self.assertTrue(finishing_plan_name)
				self.assertTrue(
					frappe.db.exists(
						"Goods Received Note",
						{
							"against": "Work Order",
							"against_id": work_order.name,
							"docstatus": 1,
							"is_return": 1,
						},
					)
				)

				rebuild_work_order_piece_tracking(
					work_order.name, check_permission=False
				)
				finishing_plan = frappe.get_doc("Finishing Plan", finishing_plan_name)

				if source_type == "Stitching":
					process = frappe.db.get_single_value(
						"MRP Settings", "finishing_inward_process"
					)
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
		for row in frappe.get_doc("Work Order", name).work_order_calculated_items:
			delivered += row.delivered_quantity
			received += row.received_qty
	return delivered, received
