from unittest import TestCase
from unittest.mock import patch

import frappe

from essdee_yrp.migration import repair_rework_item_warehouse as repair

CANDIDATES = [
	frappe._dict(name="RW-1", warehouse="Transit", to_warehouse="Final", grn_number="GRN-1", conversions=0),
	frappe._dict(name="RW-2", warehouse="Transit", to_warehouse="Final", grn_number="GRN-2", conversions=2),
]


class TestRepairReworkItemWarehouse(TestCase):
	def run_repair(self, apply):
		with (
			patch.object(repair, "get_candidates", return_value=CANDIDATES),
			patch.object(repair.frappe.db, "set_value") as set_value,
			patch.object(repair.frappe.db, "commit"),
		):
			result = repair.run(apply=apply, verbose=0)
		return result, set_value

	def test_dry_run_reports_without_writing(self):
		result, set_value = self.run_repair(apply=0)
		set_value.assert_not_called()
		self.assertEqual(result, {"candidates": 2, "cleared_from_transit": ["RW-2"], "applied": False})

	def test_apply_points_rework_items_at_the_delivery_warehouse(self):
		_result, set_value = self.run_repair(apply=1)
		self.assertEqual(
			[call.args for call in set_value.call_args_list],
			[
				("SD YRP GRN Rework Item", "RW-1", "warehouse", "Final"),
				("SD YRP GRN Rework Item", "RW-2", "warehouse", "Final"),
			],
		)

	def test_candidate_query_runs(self):
		self.assertIsInstance(repair.get_candidates(), list)
