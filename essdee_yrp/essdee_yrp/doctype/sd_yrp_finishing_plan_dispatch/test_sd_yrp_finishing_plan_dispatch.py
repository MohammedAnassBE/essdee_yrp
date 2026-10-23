from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase

from essdee_yrp.essdee_yrp.doctype.sd_yrp_finishing_plan_dispatch import (
	sd_yrp_finishing_plan_dispatch as finishing_plan_dispatch,
)

DISPATCH_ARGS = ("FPD-TEST", "SUP-FROM", "WH-FROM", "SUP-TO", "WH-TO", "TEST-1", 1)


class TestFinishingPlanDispatch(IntegrationTestCase):
	def test_new_dispatch_uses_configured_current_fiscal_series(self):
		with patch.object(
			finishing_plan_dispatch.frappe.db,
			"get_single_value",
			side_effect=["2026-04-01", "2027-03-31"],
		):
			series = finishing_plan_dispatch.get_current_fiscal_naming_series("2026-08-27")
		self.assertEqual(series, "FPD-2627-")

		# Desk's new-form loader builds a transient document without __islocal.
		doc = frappe.get_doc({"doctype": "SD YRP Finishing Plan Dispatch"})
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
		doc = frappe.new_doc("SD YRP Finishing Plan Dispatch")
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
				finishing_plan_dispatch.create_stock_dispatch(*DISPATCH_ARGS)
		dispatch.check_permission.assert_called_once_with("write")

	def test_stock_dispatch_rejects_draft_document(self):
		dispatch = MagicMock(docstatus=0, stock_entry=None)
		with patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=dispatch):
			with self.assertRaisesRegex(frappe.ValidationError, "Submit the Finishing Plan Dispatch"):
				finishing_plan_dispatch.create_stock_dispatch(*DISPATCH_ARGS)

	def test_stock_dispatch_rejects_existing_active_stock_entry(self):
		dispatch = MagicMock(docstatus=1, stock_entry="STE-TEST")
		with (
			patch.object(finishing_plan_dispatch.frappe, "get_doc", return_value=dispatch),
			patch.object(finishing_plan_dispatch.frappe.db, "get_value", return_value=1),
		):
			with self.assertRaisesRegex(frappe.ValidationError, "already exists"):
				finishing_plan_dispatch.create_stock_dispatch(*DISPATCH_ARGS)

	def test_cancel_cascades_to_submitted_dispatch_stock_entry(self):
		stock_entry = MagicMock(docstatus=1)
		doc = frappe.get_doc({"doctype": "SD YRP Finishing Plan Dispatch", "stock_entry": "STE-TEST"})
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
					against_id="FP-TEST",
					packing_source="",
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
			patch.object(finishing_plan_dispatch, "get_dispatch_locations", return_value={}),
			patch.object(finishing_plan_dispatch, "populate_stock_rates") as populate_rates,
		):
			result = finishing_plan_dispatch.create_stock_dispatch(*DISPATCH_ARGS)

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
				"doctype": "SD YRP Finishing Plan Dispatch",
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
				"doctype": "SD YRP Finishing Plan Dispatch",
				"finishing_items": frappe.as_json([selected, _item_row("FP-UNSELECTED")]),
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
		get_doc.assert_called_once_with("SD YRP Finishing Plan", "FP-SELECTED")

	def test_empty_dispatch_cannot_submit(self):
		doc = frappe.get_doc({"doctype": "SD YRP Finishing Plan Dispatch"})
		with self.assertRaisesRegex(frappe.ValidationError, "Select at least one Finishing Plan"):
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


PRINT_CONTEXT = {
	"primary": "Size",
	"cutting_by_size": {"S": 40, "M": 40, "L": 40},
	"pieces_per_box": 4,
	"components_by_size": {},
	"packing_summary": frappe._dict(dynamic_ratio_packing=False),
}
LOT_VALUES = {"production_detail": "IPD-PRINT", "pack_out_stage": "Pack", "packing_uom": "Box"}


def _print_variant(size, quantity, **values):
	return {
		"against_id": "FP-PRINT",
		"item_variant": f"ITEM-{size}",
		"uom": "Pieces",
		"quantity": quantity,
		**values,
	}


class TestFinishingPlanDispatchPrint(IntegrationTestCase):
	def _print_row(self, variants, is_submitted, grn_details=()):
		with (
			patch.object(
				finishing_plan_dispatch, "_get_dispatch_snapshot_context", return_value=PRINT_CONTEXT
			),
			patch.object(
				finishing_plan_dispatch,
				"get_variant_attr_details",
				side_effect=lambda variant: {"Size": variant.removeprefix("ITEM-")},
			),
			patch.object(
				finishing_plan_dispatch,
				"get_attribute_details",
				return_value={"primary_attribute_values": ["S", "M", "L", "XL"]},
			),
			patch.object(
				finishing_plan_dispatch.attribute_db,
				"get_value",
				side_effect=lambda doctype, name, field: LOT_VALUES[field],
			),
			patch.object(finishing_plan_dispatch.frappe, "get_all", return_value=list(grn_details)),
		):
			return finishing_plan_dispatch.get_dispatch_print_row("LOT-PRINT", "ITEM", variants, is_submitted)

	def test_submitted_print_uses_frozen_snapshot_for_dispatched_sizes(self):
		row = self._print_row(
			[
				_print_variant("M", 3, total_dispatched=7, dispatch_pct=70),
				_print_variant("S", 2, total_dispatched=5, dispatch_pct=50),
			],
			is_submitted=True,
		)
		self.assertEqual(row["sizes"], ["S", "M"])
		self.assertEqual(row["stage"], "Pack")
		self.assertEqual(row["uom"], "Pieces")
		self.assertEqual(
			row["size_data"]["M"], {"dispatch_qty": 3, "dispatch_pct": 70, "total_dispatched": 7}
		)
		self.assertEqual((row["total_dispatch"], row["total_dispatched_all"]), (5, 12))

	def test_draft_print_lists_every_cut_size_with_live_progress(self):
		grn_details = [frappe._dict(item_variant="ITEM-S", dispatched=4)]
		row = self._print_row([_print_variant("S", 1)], is_submitted=False, grn_details=grn_details)
		self.assertEqual(row["sizes"], ["S", "M", "L"])
		self.assertEqual(
			row["size_data"]["S"], {"dispatch_qty": 1, "dispatch_pct": 40, "total_dispatched": 4}
		)
		self.assertEqual(row["size_data"]["M"], {"dispatch_qty": 0, "dispatch_pct": 0, "total_dispatched": 0})

	def test_batch_dispatch_prints_lot_packing_uom(self):
		variant = _print_variant("S", 2, packing_source="batch", packing_piece_quantity=8)
		row = self._print_row([variant], is_submitted=True)
		self.assertEqual((row["uom"], row["size_data"]["S"]["dispatch_qty"]), ("Box", 8))

	def test_dispatch_print_format_is_the_default(self):
		self.assertEqual(
			frappe.get_meta("SD YRP Finishing Plan Dispatch").default_print_format,
			"Essdee Finishing Plan Dispatch",
		)
