from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan_dispatch import (
	sd_yrp_finishing_plan_dispatch as finishing_plan_dispatch,
)


class TestFinishingPlanDispatch(IntegrationTestCase):
	def test_new_dispatch_uses_configured_current_fiscal_series(self):
		with patch.object(
			finishing_plan_dispatch.frappe.db,
			"get_single_value",
			side_effect=["2026-04-01", "2027-03-31"],
		):
			series = finishing_plan_dispatch.get_current_fiscal_naming_series(
				"2026-08-27"
			)
		self.assertEqual(series, "FPD-2627-")

		# Desk's new-form loader builds a transient document without __islocal.
		doc = frappe.get_doc({"doctype": 'SD YRP Finishing Plan Dispatch'})
		with patch.object(
			finishing_plan_dispatch,
			"get_current_fiscal_naming_series",
			return_value=series,
		):
			doc.onload()
		self.assertEqual(doc.naming_series, series)

	def test_fiscal_series_rejects_date_outside_configured_window(self):
		with patch.object(
			finishing_plan_dispatch.frappe.db,
			"get_single_value",
			side_effect=["2026-04-01", "2027-03-31"],
		):
			with self.assertRaisesRegex(frappe.ValidationError, "outside the configured"):
				finishing_plan_dispatch.get_current_fiscal_naming_series("2027-04-01")

	def test_fresh_dispatch_rejects_non_current_series_server_side(self):
		doc = frappe.new_doc('SD YRP Finishing Plan Dispatch')
		doc.naming_series = "FPD-2526-"
		with patch.object(
			finishing_plan_dispatch,
			"get_current_fiscal_naming_series",
			return_value="FPD-2627-",
		):
			with self.assertRaisesRegex(frappe.ValidationError, "must be FPD-2627-"):
				doc.validate()

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
			{"doctype": 'SD YRP Finishing Plan Dispatch', "stock_entry": "STE-TEST"}
		)
		with patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=stock_entry):
			doc.before_cancel()
		stock_entry.cancel.assert_called_once_with()

	def test_stock_dispatch_populates_dimension_aware_rates_before_insert(self):
		dispatch = SimpleNamespace(
			docstatus=1,
			stock_entry=None,
			packing_batch_dispatch_json=None,
			dispatch_colour_details=None,
			finishing_plan_dispatch_items=[
				SimpleNamespace(
					item_variant="ITEM-S",
					quantity=4,
					lot="LOT-1",
					uom="Pieces",
				)
			],
			check_permission=MagicMock(),
		)
		stock_entry = MagicMock()
		stock_entry.name = "STE-TEST"
		with (
			patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=dispatch),
			patch.object(finishing_plan_dispatch.frappe, "new_doc", return_value=stock_entry),
			patch.object(
				finishing_plan_dispatch.frappe.db,
				"get_single_value",
				return_value="Accepted",
			),
			patch.object(finishing_plan_dispatch, "populate_stock_rates") as populate_rates,
		):
			result = finishing_plan_dispatch.create_stock_dispatch(
				"FPD-TEST", "WH-FROM", "SUP-TO", "TEST-1", 100
			)

		self.assertEqual(result, "STE-TEST")
		populate_rates.assert_called_once_with(stock_entry, "WH-FROM")
		stock_entry.insert.assert_called_once_with()
		stock_entry.submit.assert_called_once_with()

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
				"doctype": 'SD YRP Finishing Plan Dispatch',
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
				"doctype": 'SD YRP Finishing Plan Dispatch',
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
		get_doc.assert_called_once_with('SD YRP Finishing Plan', "FP-SELECTED")

	def test_empty_dispatch_cannot_submit(self):
		doc = frappe.get_doc({"doctype": 'SD YRP Finishing Plan Dispatch'})
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
