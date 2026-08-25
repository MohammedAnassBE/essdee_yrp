from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.finishing_plan_dispatch import (
	finishing_plan_dispatch,
)


class TestFinishingPlanDispatch(IntegrationTestCase):
	def test_stock_dispatch_requires_write_permission(self):
		dispatch = MagicMock(docstatus=1, stock_entry=None)
		dispatch.check_permission.side_effect = frappe.PermissionError
		with patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=dispatch):
			with self.assertRaises(frappe.PermissionError):
				finishing_plan_dispatch.create_stock_dispatch(
					"FPD-TEST", "WH-FROM", "SUP-TO", "TEST-1", 1
				)
		dispatch.check_permission.assert_called_once_with("write")

	def test_stock_dispatch_rejects_draft_document(self):
		dispatch = MagicMock(docstatus=0, stock_entry=None)
		with patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=dispatch):
			with self.assertRaisesRegex(frappe.ValidationError, "Submit the Finishing Plan Dispatch"):
				finishing_plan_dispatch.create_stock_dispatch(
					"FPD-TEST", "WH-FROM", "SUP-TO", "TEST-1", 1
				)

	def test_stock_dispatch_rejects_existing_active_stock_entry(self):
		dispatch = MagicMock(docstatus=1, stock_entry="STE-TEST")
		with (
			patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=dispatch),
			patch.object(finishing_plan_dispatch.frappe.db, "get_value", return_value=1),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "already exists"):
				finishing_plan_dispatch.create_stock_dispatch(
					"FPD-TEST", "WH-FROM", "SUP-TO", "TEST-1", 1
				)

	def test_cancel_cascades_to_submitted_dispatch_stock_entry(self):
		stock_entry = MagicMock(docstatus=1)
		doc = frappe.get_doc(
			{"doctype": "Finishing Plan Dispatch", "stock_entry": "STE-TEST"}
		)
		with patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=stock_entry):
			doc.before_cancel()
		stock_entry.cancel.assert_called_once_with()

	def test_draft_merge_keeps_valid_batch_selection_only(self):
		fresh = _item_row("FP-1")
		fresh.update(
			{
				"dynamic_ratio_packing": True,
				"packing_batches": [{"batch_row": "BATCH-CURRENT"}],
			}
		)
		saved = _item_row("FP-1")
		saved["batch_dispatches"] = [
			{"batch_row": "BATCH-CURRENT", "box_quantity": 2},
			{"batch_row": "BATCH-REMOVED", "box_quantity": 1},
		]

		merged = finishing_plan_dispatch.merge_saved_finishing_items([fresh], [saved])

		self.assertEqual(
			merged[0]["batch_dispatches"],
			[{"batch_row": "BATCH-CURRENT", "box_quantity": 2}],
		)

	def test_zero_quantity_legacy_rows_are_not_persisted(self):
		doc = frappe.get_doc(
			{
				"doctype": "Finishing Plan Dispatch",
				"finishing_items": frappe.as_json([_item_row("FP-LEGACY")]),
			}
		)
		fp_doc = SimpleNamespace(
			name="FP-LEGACY",
			check_permission=lambda *_args, **_kwargs: None,
		)
		with (
			patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=fp_doc) as get_doc,
			patch.object(
				finishing_plan_dispatch,
				"get_finishing_packing_summary",
				return_value=frappe._dict(dynamic_ratio_packing=False),
			),
			patch.object(finishing_plan_dispatch, "get_or_create_variant") as create_variant,
		):
			doc.before_validate()

		self.assertEqual(len(doc.finishing_plan_dispatch_items), 0)
		self.assertEqual(frappe.parse_json(doc.finishing_items), [])
		get_doc.assert_not_called()
		create_variant.assert_not_called()

	def test_only_selected_plan_is_kept_in_dispatch_snapshot(self):
		selected = _item_row("FP-SELECTED")
		selected["values"]["S"]["dispatch_qty"] = 3
		doc = frappe.get_doc(
			{
				"doctype": "Finishing Plan Dispatch",
				"finishing_items": frappe.as_json(
					[selected, _item_row("FP-UNSELECTED")]
				),
			}
		)
		fp_doc = SimpleNamespace(
			name="FP-SELECTED",
			check_permission=lambda *_args, **_kwargs: None,
		)
		with (
			patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=fp_doc) as get_doc,
			patch.object(
				finishing_plan_dispatch,
				"get_finishing_packing_summary",
				return_value=frappe._dict(dynamic_ratio_packing=False),
			),
			patch.object(finishing_plan_dispatch, "build_variant_attributes", return_value={}),
			patch.object(finishing_plan_dispatch, "get_or_create_variant", return_value="ITEM-S"),
		):
			doc.before_validate()

		self.assertEqual(
			[row["doc_name"] for row in frappe.parse_json(doc.finishing_items)],
			["FP-SELECTED"],
		)
		get_doc.assert_called_once_with("Finishing Plan", "FP-SELECTED")

	def test_empty_dispatch_cannot_submit(self):
		doc = frappe.get_doc({"doctype": "Finishing Plan Dispatch"})
		with self.assertRaisesRegex(
			frappe.ValidationError, "Select at least one Finishing Plan"
		):
			doc.before_submit()


def _item_row(finishing_plan):
	return {
		"doc_name": finishing_plan,
		"lot": f"LOT-{finishing_plan}",
		"item": "ITEM-TEST",
		"uom": "Pieces",
		"primary_attribute": "Size",
		"stage": "Packed",
		"values": {
			"S": {
				"qty": 20,
				"row_detail": f"FP-GRN-{finishing_plan}",
				"dispatch_qty": 0,
			}
		},
		"batch_dispatches": [],
	}
