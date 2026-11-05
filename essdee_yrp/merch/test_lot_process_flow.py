import datetime
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from essdee_yrp.merch import lot_process_data as data_module
from essdee_yrp.merch import lot_process_flow as flow

DATA = "essdee_yrp.merch.lot_process_data"


def day(value):
	return datetime.date.fromisoformat(value)


class TestLotProcessFlow(TestCase):
	def test_unreadable_lot_raises_before_any_query(self):
		doc = MagicMock()
		doc.check_permission.side_effect = frappe.PermissionError
		with patch(f"{DATA}.frappe.get_doc", return_value=doc), patch(f"{DATA}.frappe.get_list") as get_list:
			with self.assertRaises(frappe.PermissionError):
				flow.get_process_flow("LOT-1")
		get_list.assert_not_called()

	def test_unreadable_work_order_raises(self):
		with patch(f"{DATA}.frappe.get_list", return_value=[]):
			with self.assertRaises(frappe.PermissionError):
				flow.get_work_order_detail("WO-1")

	def test_movement_dates_use_posting_dates_and_skip_returns(self):
		dcs = [
			{"work_order": "WO-1", "posting_date": day("2026-10-22")},
			{"work_order": "WO-1", "posting_date": day("2026-10-20")},
		]
		grns = [
			{"against_id": "WO-1", "posting_date": day("2026-10-25"), "is_return": 0},
			{"against_id": "WO-1", "posting_date": day("2026-10-30"), "is_return": 1},
			{"against_id": "WO-2", "posting_date": day("2026-10-26"), "is_return": 0},
		]
		self.assertEqual(
			data_module.movement_dates(dcs, grns),
			{
				"WO-1": (day("2026-10-20"), day("2026-10-25")),
				"WO-2": (None, day("2026-10-26")),
			},
		)

	def test_packing_counts_only_the_packing_work_order_grns(self):
		data = data_module.LotFlowData.__new__(data_module.LotFlowData)
		data.doc = frappe._dict(name="LOT-1", packing_combo=5, total_order_quantity=100)
		data.ipd = frappe._dict(packing_combo=5, primary_item_attribute="Size")
		data.__dict__.update(
			{
				"documents": (
					[],
					[
						{
							"name": "GRN-PACK",
							"against_id": "WO-PACK",
							"is_return": 0,
							"packing_calculation_version": 0,
						},
						{
							"name": "GRN-OTHER",
							"against_id": "WO-STITCH",
							"is_return": 0,
							"packing_calculation_version": 0,
						},
						{
							"name": "GRN-RETURN",
							"against_id": "WO-PACK",
							"is_return": 1,
							"packing_calculation_version": 0,
						},
					],
				),
				"plans": {"cutting": {}, "finishing": []},
				"calculated_items": [],
				"order_rows": [],
				"sizes": ["S"],
				"parts": 1,
			}
		)
		child_rows = MagicMock(
			side_effect=lambda doctype, parents, fields, parenttype: (
				[{"parent": name, "item_variant": "V-S", "quantity": 2} for name in parents]
				if doctype == "YRP Goods Received Note Item"
				else []
			)
		)
		with (
			patch(f"{DATA}.quantities.child_rows", child_rows),
			patch(f"{DATA}.quantities.variant_attributes", return_value={"V-S": {"Size": "S"}}),
		):
			packing = data.packing({"WO-PACK"})
		self.assertEqual(packing["received"], {"S": 10})
		grn_call = next(
			call for call in child_rows.call_args_list if call.args[0] == "YRP Goods Received Note Item"
		)
		self.assertEqual(list(grn_call.args[1]), ["GRN-PACK"])
